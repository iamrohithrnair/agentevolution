"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Wifi, WifiOff } from "lucide-react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { fetchLiveKitToken } from "@/lib/livekit";

interface Props {
  missionId?: string;
}

type Speaker = "user" | "agent" | "idle";

/**
 * Voice console — real FFT waveform driven by the LiveKit room's local mic
 * and remote agent audio tracks. Indigo bars represent the user speaking,
 * green bars the agent replying. Colour shifts to whoever is loudest.
 */
export function VoiceHUD({ missionId }: Props) {
  const [mode, setMode] = useState<"ptt" | "always_on">("always_on");
  const [language, setLanguage] = useState<"en" | "auto">("en");
  const [joining, setJoining] = useState(false);
  const [joined, setJoined] = useState(false);
  const [pressed, setPressed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speaker, setSpeaker] = useState<Speaker>("idle");

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const roomRef = useRef<unknown>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);

  // Web Audio handles. One AudioContext per session; separate analyser per
  // direction so we can tell who's talking. Stored in refs because the draw
  // loop needs the latest values without re-rendering.
  const audioCtxRef = useRef<AudioContext | null>(null);
  const localAnalyserRef = useRef<AnalyserNode | null>(null);
  const remoteAnalyserRef = useRef<AnalyserNode | null>(null);

  function ensureAudioCtx(): AudioContext {
    if (!audioCtxRef.current) {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioCtxRef.current = new AC();
    }
    return audioCtxRef.current;
  }

  function attachAnalyser(
    track: MediaStreamTrack,
    target: "local" | "remote",
  ): void {
    try {
      const ctx = ensureAudioCtx();
      const src = ctx.createMediaStreamSource(new MediaStream([track]));
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.7;
      src.connect(analyser);
      if (target === "local") localAnalyserRef.current = analyser;
      else remoteAnalyserRef.current = analyser;
    } catch {
      /* ignore — some browsers block AudioContext until a user gesture */
    }
  }

  // Main draw loop — runs while joined.
  useEffect(() => {
    if (!joined) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx2d = canvas.getContext("2d");
    if (!ctx2d) return;

    let raf = 0;
    const bars = 48;
    const localData = new Uint8Array(128);
    const remoteData = new Uint8Array(128);

    const draw = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * devicePixelRatio || canvas.height !== h * devicePixelRatio) {
        canvas.width = w * devicePixelRatio;
        canvas.height = h * devicePixelRatio;
        ctx2d.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
      }
      ctx2d.clearRect(0, 0, w, h);

      // Read FFT from whichever analysers are live.
      let localLevel = 0;
      let remoteLevel = 0;
      if (localAnalyserRef.current) {
        localAnalyserRef.current.getByteFrequencyData(localData);
        localLevel = arrAvg(localData);
      }
      if (remoteAnalyserRef.current) {
        remoteAnalyserRef.current.getByteFrequencyData(remoteData);
        remoteLevel = arrAvg(remoteData);
      }

      // Pick active speaker (fade threshold 8 to ignore noise floor).
      let active: Speaker = "idle";
      if (remoteLevel > 8 && remoteLevel >= localLevel) active = "agent";
      else if (localLevel > 8) active = "user";
      if (active !== speaker) setSpeaker(active);

      // Layer local (indigo) + remote (green). Active speaker draws on top.
      drawBars(ctx2d, w, h, localData, bars, "rgba(99, 102, 241, 0.55)"); // indigo-500
      drawBars(ctx2d, w, h, remoteData, bars, "rgba(21, 128, 61, 0.70)"); // green-700

      // Centre idle pulse if nobody is speaking.
      if (active === "idle") {
        ctx2d.fillStyle = "rgba(148, 163, 184, 0.35)"; // slate-400
        const pulse = 3 + Math.sin(Date.now() / 400) * 1.2;
        ctx2d.beginPath();
        ctx2d.arc(w / 2, h / 2, pulse, 0, Math.PI * 2);
        ctx2d.fill();
      }

      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [joined, speaker]);

  async function join() {
    setJoining(true);
    setError(null);
    try {
      const session = await fetchLiveKitToken({
        mode,
        language,
        ...(missionId !== undefined ? { missionId } : {}),
      });

      if (!session.url || !session.token) {
        setJoined(true);
        return;
      }

      const { Room, RoomEvent, Track } = await import("livekit-client");
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        publishDefaults: { dtx: true, audioPreset: { maxBitrate: 32_000 } },
      });
      roomRef.current = room;

      // Remote audio → analyser + hidden <audio> so the operator hears it.
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== Track.Kind.Audio) return;
        if (!audioElRef.current) {
          const el = document.createElement("audio");
          el.autoplay = true;
          el.style.display = "none";
          document.body.appendChild(el);
          audioElRef.current = el;
        }
        track.attach(audioElRef.current!);
        const mst = (track as unknown as { mediaStreamTrack?: MediaStreamTrack })
          .mediaStreamTrack;
        if (mst) attachAnalyser(mst, "remote");
      });

      // Local mic → analyser only. LiveKit publishes the track itself.
      room.on(RoomEvent.LocalTrackPublished, (pub) => {
        const track = (pub as unknown as { track?: { kind?: unknown; mediaStreamTrack?: MediaStreamTrack } }).track;
        if (track && track.kind === Track.Kind.Audio && track.mediaStreamTrack) {
          attachAnalyser(track.mediaStreamTrack, "local");
        }
      });

      await room.connect(session.url, session.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setJoined(true);
    } catch (e) {
      setError((e as Error).message || "Failed to join voice room");
      setJoined(false);
    } finally {
      setJoining(false);
    }
  }

  async function leave() {
    try {
      const r = roomRef.current as { disconnect?: () => Promise<void> } | null;
      await r?.disconnect?.();
    } catch {
      // best effort
    }
    roomRef.current = null;
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current.remove();
      audioElRef.current = null;
    }
    if (audioCtxRef.current) {
      try {
        await audioCtxRef.current.close();
      } catch {
        /* ignore */
      }
      audioCtxRef.current = null;
    }
    localAnalyserRef.current = null;
    remoteAnalyserRef.current = null;
    setSpeaker("idle");
    setJoined(false);
  }

  const speakerBadge = {
    user: { text: "you · speaking", klass: "bg-indigo-100 text-indigo-700 border-indigo-200" },
    agent: { text: "agent · speaking", klass: "bg-green-100 text-green-700 border-green-200" },
    idle: { text: "listening", klass: "bg-slate-100 text-slate-600 border-slate-200" },
  }[speaker];

  return (
    <Card className="flex h-full flex-col" data-testid="voice-hud">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle>Voice console</CardTitle>
        <Badge variant={joined ? "success" : "outline"} className="gap-1.5">
          {joined ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          {joined ? "live · LiveKit room" : "preview"}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <div className="relative h-24 overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)]">
          {joined ? (
            <>
              <canvas ref={canvasRef} className="h-full w-full" />
              <div
                className={`pointer-events-none absolute left-2 top-2 rounded-full border px-2 py-0.5 text-[10px] ${speakerBadge.klass}`}
              >
                {speakerBadge.text}
              </div>
            </>
          ) : (
            <div className="grid h-full place-items-center text-center text-xs text-[var(--color-fg-muted)]">
              Join the room to see the live waveform. Your voice shows indigo; the agent shows green.
            </div>
          )}
          {pressed && (
            <motion.div
              layoutId="ptt-halo"
              className="pointer-events-none absolute inset-0 rounded-md ring-2 ring-[var(--color-danger)]/40"
            />
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <label className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
            <span className="text-[var(--color-fg-muted)]">Always-on</span>
            <Switch
              checked={mode === "always_on"}
              onCheckedChange={(v) => setMode(v ? "always_on" : "ptt")}
              aria-label="Always on"
            />
          </label>
          <label className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
            <span className="text-[var(--color-fg-muted)]">Auto-detect language</span>
            <Switch
              checked={language === "auto"}
              onCheckedChange={(v) => setLanguage(v ? "auto" : "en")}
              aria-label="Auto language"
            />
          </label>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant={joined ? "outline" : "default"}
            disabled={joining}
            onClick={() => (joined ? void leave() : void join())}
            className="flex-1 gap-1.5"
          >
            {joining ? "Joining…" : joined ? "Leave room" : "Join voice room"}
          </Button>
          {mode === "ptt" && (
            <Button
              variant={pressed ? "danger" : "soft"}
              aria-pressed={pressed}
              disabled={!joined}
              onMouseDown={async () => {
                setPressed(true);
                const r = roomRef.current as
                  | { localParticipant?: { setMicrophoneEnabled: (v: boolean) => Promise<void> } }
                  | null;
                await r?.localParticipant?.setMicrophoneEnabled?.(true);
              }}
              onMouseUp={async () => {
                setPressed(false);
                const r = roomRef.current as
                  | { localParticipant?: { setMicrophoneEnabled: (v: boolean) => Promise<void> } }
                  | null;
                await r?.localParticipant?.setMicrophoneEnabled?.(false);
              }}
              onMouseLeave={() => pressed && setPressed(false)}
              className="gap-1.5"
            >
              {pressed ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
              Hold
            </Button>
          )}
        </div>

        {error && (
          <p className="text-xs text-[var(--color-danger)]" role="alert">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function arrAvg(arr: Uint8Array): number {
  let sum = 0;
  for (let i = 0; i < arr.length; i++) sum += arr[i]!;
  return sum / arr.length;
}

function drawBars(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  data: Uint8Array,
  bars: number,
  color: string,
): void {
  if (!data.some((v) => v > 0)) return;
  ctx.fillStyle = color;
  const step = Math.floor(data.length / bars);
  const gap = 2;
  const barWidth = Math.max(2, (w - gap * (bars - 1)) / bars);
  for (let i = 0; i < bars; i++) {
    const v = data[i * step] ?? 0;
    const bh = Math.max(2, (v / 255) * h * 0.9);
    const x = i * (barWidth + gap);
    const y = h / 2 - bh / 2;
    const r = Math.min(2, barWidth / 2);
    // Rounded rect (roundRect is not in lib.dom across TS versions yet).
    ctx.beginPath();
    const rr = (ctx as unknown as {
      roundRect?: (x: number, y: number, w: number, h: number, r: number) => void;
    }).roundRect;
    if (rr) {
      rr.call(ctx, x, y, barWidth, bh, r);
    } else {
      (ctx as CanvasRenderingContext2D).rect(x, y, barWidth, bh);
    }
    ctx.fill();
  }
}
