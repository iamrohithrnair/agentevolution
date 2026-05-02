/**
 * `/api/agents/stream` SSE consumer (prompts §3.18) used by the
 * Memory Inspector, Reasoning Stream, and Reflection Feed.
 *
 * In mock mode we bridge `agent_message` events from the in-memory simulator
 * into the same callback signature.
 */

import env from "./env";
import { getMockAgentMessages, onMockEvent } from "./mock";
import type { AgentMessage } from "./types";

export interface AgentsStreamFilter {
  kind?: AgentMessage["kind"];
  mission_id?: string;
  operator_id?: string;
}

export function openAgentsStream(
  filter: AgentsStreamFilter,
  onMessage: (m: AgentMessage) => void,
): () => void {
  if (env.useMocks) {
    // Replay last 50 matching messages so newcomers get context.
    const replay = getMockAgentMessages(filter).slice(0, 50).reverse();
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      for (const m of replay) onMessage(m);
    });
    const off = onMockEvent((event) => {
      if (event.type !== "agent_message") return;
      const m = event.message;
      if (filter.kind && m.kind !== filter.kind) return;
      if (filter.mission_id && m.mission_id !== filter.mission_id) return;
      if (filter.operator_id && m.operator_id !== filter.operator_id) return;
      onMessage(m);
    });
    return () => {
      cancelled = true;
      off();
    };
  }

  const qs = new URLSearchParams();
  if (filter.kind) qs.set("kind", filter.kind);
  if (filter.mission_id) qs.set("mission_id", filter.mission_id);
  if (filter.operator_id) qs.set("operator_id", filter.operator_id);
  const url = `${env.apiBase}/api/agents/stream?${qs.toString()}`;

  let es: EventSource | null = null;
  try {
    es = new EventSource(url, { withCredentials: true });
  } catch {
    return () => undefined;
  }
  const handler = (e: MessageEvent) => {
    try {
      const m = JSON.parse(e.data) as AgentMessage;
      onMessage(m);
    } catch {
      /* skip malformed */
    }
  };
  es.addEventListener("message", handler);
  return () => {
    es?.removeEventListener("message", handler);
    es?.close();
  };
}
