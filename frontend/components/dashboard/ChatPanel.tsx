"use client";

import { useRef, useState } from "react";
import { Loader2, SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchChatSSE, createMission } from "@/lib/api";
import { toast } from "sonner";

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  partial?: boolean;
}

const SUGGESTIONS = [
  "Dispatch O-neg blood to Royal London — critical.",
  "Send insulin and a defibrillator to King's College.",
  "What's the weather on the corridor to Homerton?",
];

interface Props {
  missionId?: string;
  compact?: boolean;
}

export function ChatPanel({ missionId, compact }: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const formRef = useRef<HTMLFormElement | null>(null);

  async function send(messageOverride?: string) {
    const message = (messageOverride ?? draft).trim();
    if (!message || streaming) return;
    const userId = `u_${Date.now()}`;
    const aId = `a_${Date.now()}`;
    setTurns((t) => [
      ...t,
      { id: userId, role: "user", text: message },
      { id: aId, role: "assistant", text: "", partial: true },
    ]);
    setDraft("");
    setStreaming(true);
    try {
      let buf = "";
      for await (const ev of fetchChatSSE(message, missionId ? { mission_id: missionId } : {})) {
        if (ev.event === "token") {
          const text = (ev.data as { text?: string }).text ?? "";
          buf += text;
          setTurns((t) =>
            t.map((x) => (x.id === aId ? { ...x, text: buf } : x)),
          );
        } else if (ev.event === "tool") {
          const name = (ev.data as { name?: string }).name ?? "tool";
          buf += `\n\n› invoking ${name}…`;
          setTurns((t) => t.map((x) => (x.id === aId ? { ...x, text: buf } : x)));
        } else if (ev.event === "done") {
          setTurns((t) => t.map((x) => (x.id === aId ? { ...x, partial: false } : x)));
        }
      }

      // Demo helper: if the user said "dispatch", actually create a mission.
      if (/dispatch|send|deliver/i.test(message)) {
        try {
          const r = await createMission({
            deliveries: [
              {
                destination_id: /king/i.test(message) ? "fac_kings" : "fac_royal_london",
                supply: /defib/i.test(message)
                  ? "defib"
                  : /insulin/i.test(message)
                    ? "insulin"
                    : "o_neg_blood",
                payload_weight_kg: 1.2,
                priority: /critical/i.test(message) ? "critical" : "high",
                cold_chain_required: /blood|insulin|vaccine/i.test(message),
              },
            ],
            scenario: "Chat dispatch",
          });
          toast.success(`Mission ${r.mission_id.slice(-6)} dispatched · ETA ${r.eta_seconds}s`);
        } catch (e) {
          toast.error(`Dispatch failed: ${(e as Error).message}`);
        }
      }
    } catch (e) {
      toast.error(`Chat failed: ${(e as Error).message}`);
      setTurns((t) => t.map((x) => (x.id === aId ? { ...x, text: "Error.", partial: false } : x)));
    } finally {
      setStreaming(false);
    }
  }

  return (
    <Card className="flex h-full flex-col" data-testid="chat-panel">
      <CardHeader className="flex-row items-center justify-between gap-2 pb-2">
        <CardTitle>{compact ? "Mission chat" : "Mission Control · text"}</CardTitle>
        <Badge variant="outline">SSE · /api/chat</Badge>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3 pb-3">
        <div className="thin-scrollbar flex-1 space-y-3 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
          {turns.length === 0 ? (
            <p className="text-sm text-[var(--color-fg-muted)]">
              Ask Mission Control to dispatch a delivery, or pick a suggestion below.
            </p>
          ) : (
            turns.map((t) => <ChatBubble key={t.id} turn={t} />)
          )}
        </div>

        {turns.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <Button
                key={s}
                variant="outline"
                size="sm"
                className="h-7 px-2.5 text-[11px]"
                onClick={() => send(s)}
              >
                {s}
              </Button>
            ))}
          </div>
        )}

        <form
          ref={formRef}
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="flex items-center gap-2"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Talk to Mission Control…"
            aria-label="Message"
            className="h-9 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm placeholder:text-[var(--color-fg-subtle)] focus:outline-none focus-visible:shadow-[var(--shadow-focus)]"
          />
          <Button type="submit" disabled={streaming || !draft.trim()} className="gap-1.5">
            {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <SendHorizontal className="h-4 w-4" />}
            Send
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ChatBubble({ turn }: { turn: ChatTurn }) {
  const mine = turn.role === "user";
  return (
    <div className={mine ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          mine
            ? "max-w-[80%] whitespace-pre-wrap rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm text-[var(--color-fg-inverse)] shadow-[var(--shadow-1)]"
            : "max-w-[80%] whitespace-pre-wrap rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-fg)] shadow-[var(--shadow-1)]"
        }
      >
        {turn.text || (turn.partial ? "▍" : "")}
      </div>
    </div>
  );
}
