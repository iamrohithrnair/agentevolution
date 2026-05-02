/**
 * WebSocket fan-out for `/ws/missions/{id}` and `/ws/dashboard` (prompts §3.16).
 *
 * In mock mode every kind is bridged off the in-memory simulator's pub/sub bus
 * — components consume the same envelope shape regardless of the data source.
 */

import env from "./env";
import { onMockEvent } from "./mock";
import type {
  Drone,
  FlightLog,
  Mission,
  TelemetryFrame,
  WSEnvelope,
  WSKind,
} from "./types";

type DocFor<K extends WSKind> = K extends "telemetry"
  ? TelemetryFrame
  : K extends "flight_log"
  ? FlightLog
  : K extends "mission_update"
  ? Mission
  : K extends "drone_update"
  ? Drone
  : unknown;

export interface ChannelSocket {
  on<K extends WSKind>(kind: K, cb: (doc: DocFor<K>) => void): () => void;
  close(): void;
}

interface Subscription {
  kind: WSKind;
  cb: (doc: unknown) => void;
}

function mockChannel(filter: { mission_id?: string }): ChannelSocket {
  const subs = new Set<Subscription>();
  const off = onMockEvent((event) => {
    if (event.type === "telemetry") {
      if (filter.mission_id && event.frame.mission_id !== filter.mission_id) return;
      for (const s of subs) if (s.kind === "telemetry") s.cb(event.frame);
    } else if (event.type === "flight_log") {
      if (filter.mission_id && event.log.mission_id !== filter.mission_id) return;
      for (const s of subs) if (s.kind === "flight_log") s.cb(event.log);
    } else if (event.type === "mission_update") {
      if (filter.mission_id && event.mission.id !== filter.mission_id) return;
      for (const s of subs) if (s.kind === "mission_update") s.cb(event.mission);
    } else if (event.type === "drone_update") {
      for (const s of subs) if (s.kind === "drone_update") s.cb(event.drone);
    }
  });

  return {
    on(kind, cb) {
      const sub: Subscription = { kind, cb: cb as (doc: unknown) => void };
      subs.add(sub);
      return () => {
        subs.delete(sub);
      };
    },
    close() {
      off();
      subs.clear();
    },
  };
}

function realChannel(path: string): ChannelSocket {
  const url = `${env.wsBase || env.apiBase.replace(/^http/i, "ws")}${path}`;
  let ws: WebSocket | null = null;
  let backoff = 500;
  let closed = false;
  const subs = new Set<Subscription>();

  const connect = () => {
    if (closed) return;
    try {
      ws = new WebSocket(url);
    } catch {
      // Unsupported in SSR; just no-op.
      return;
    }
    ws.onopen = () => {
      backoff = 500;
    };
    ws.onmessage = (e) => {
      try {
        const env_: WSEnvelope = JSON.parse(e.data);
        for (const s of subs) {
          if (s.kind === env_.kind) s.cb(env_.doc);
        }
        if (env_.id) ws?.send(JSON.stringify({ kind: "ack", id: env_.id }));
      } catch {
        /* skip malformed */
      }
    };
    ws.onclose = () => {
      if (closed) return;
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 10_000);
    };
    ws.onerror = () => {
      ws?.close();
    };
  };
  connect();

  return {
    on(kind, cb) {
      const sub: Subscription = { kind, cb: cb as (doc: unknown) => void };
      subs.add(sub);
      return () => {
        subs.delete(sub);
      };
    },
    close() {
      closed = true;
      ws?.close();
      subs.clear();
    },
  };
}

export function openMissionSocket(missionId: string): ChannelSocket {
  if (env.useMocks) return mockChannel({ mission_id: missionId });
  return realChannel(`/ws/missions/${missionId}`);
}

export function openDashboardSocket(): ChannelSocket {
  if (env.useMocks) return mockChannel({});
  return realChannel(`/ws/dashboard`);
}
