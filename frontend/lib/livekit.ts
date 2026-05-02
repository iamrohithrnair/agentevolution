/**
 * LiveKit room helpers — token mint + room construction for the
 * voice console (prompts/06-voice-livekit-elevenlabs.md, prompts §5.1).
 *
 * In Phase 5 the voice layer is mocked: `fetchLiveKitToken` returns a stub
 * session that the VoiceHUD renders as "Voice channel pending — running in
 * text-mode preview", so judges still see the polished surface even without
 * LiveKit credentials.
 */

import env from "./env";
import type { LkSession } from "./types";

export type LkRoom = unknown; // Lazy-resolved at call site; avoid hard import for SSR.

export async function fetchLiveKitToken(opts: {
  mode: "ptt" | "always_on";
  language: "en" | "auto";
  missionId?: string;
}): Promise<LkSession> {
  if (env.useMocks || !env.livekitUrl) {
    return {
      url: "",
      token: "",
      room: "dronan-mock",
      identity: "operator-demo",
      mode: opts.mode,
      language: opts.language,
    };
  }
  const r = await fetch("/api/livekit-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/**
 * Lazily import `livekit-client` so the heavy media stack is only pulled in
 * when the operator actually opens the voice console.
 */
export async function createRoom(): Promise<LkRoom> {
  const { Room } = await import("livekit-client");
  return new Room({
    adaptiveStream: true,
    dynacast: true,
    publishDefaults: { dtx: true, audioPreset: { maxBitrate: 32_000 } },
  });
}

export async function publishData(room: unknown, data: object): Promise<void> {
  // The Room type from livekit-client is awaited at call sites that already
  // imported it; we keep the helper untyped to avoid a bundle-cost on pages
  // that never join a room.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const r = room as any;
  if (!r?.localParticipant?.publishData) return;
  await r.localParticipant.publishData(
    new TextEncoder().encode(JSON.stringify(data)),
    { reliable: true },
  );
}
