# 08 · Frontend — Next.js 15 + React 19 + Tailwind v4 + shadcn/ui

> **Scope.** Production-grade, demo-ready operator console for DroneFleet. Light-mode only, hospital-clean visual language. Streams from FastAPI (file 07), holds a LiveKit room (file 06), surfaces live MongoDB Change Streams.
>
> **Cross-references.**
> - HTTP/WS/SSE contracts: [`07-backend-fastapi.md`](./07-backend-fastapi.md).
> - Voice room and data-channel protocol: [`06-voice-livekit-elevenlabs.md`](./06-voice-livekit-elevenlabs.md).
> - Agent semantics surfacing in the Memory Inspector + Reflection Feed: [`04-langchain-agents.md`](./04-langchain-agents.md) and [`05-self-evolution.md`](./05-self-evolution.md).
> - Original UI to mine for typography & vibe (do **not** copy code): `DroneFleet/web/`.

---

## 0 · Stack confirmation

- **Next.js 15** App Router, **React 19** (Server Components + use() + Suspense streaming).
- **TypeScript strict** (`"strict": true`, `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`).
- **Tailwind CSS v4** with `@theme` (no `tailwind.config.js` for tokens — they live in CSS).
- **shadcn/ui** primitives (button, card, dialog, sheet, badge, tooltip, command, toggle, select, skeleton).
- **framer-motion** for micro-interactions.
- **Leaflet + react-leaflet** for 2D base map and markers.
- **deck.gl** (`@deck.gl/react`, `@deck.gl/layers`) for animated `ArcLayer` trails.
- **react-three-fiber + @react-three/drei** for the 3D drone scene.
- **livekit-client + @livekit/components-react** for the voice console.
- **lucide-react** for icons.
- **recharts** for the Self-Evolution chart.
- **sonner** for toasts.
- **NextAuth (auth.js v5)** with the MongoDB adapter for credentials + email magic link.

**Light mode only.** No dark mode toggle. The medical context demands maximal legibility under fluorescent ER lighting.

---

## 1 · Folder layout

```
web/
├── package.json
├── next.config.ts
├── tailwind.config.ts          # only `content` paths; tokens are in globals.css
├── tsconfig.json
├── postcss.config.mjs
├── app/
│   ├── layout.tsx
│   ├── page.tsx                # Landing
│   ├── (auth)/
│   │   ├── layout.tsx
│   │   ├── login/page.tsx
│   │   └── signup/page.tsx
│   ├── (app)/
│   │   ├── layout.tsx          # sidebar + topbar shell
│   │   ├── dashboard/page.tsx
│   │   ├── dispatch/page.tsx
│   │   ├── missions/page.tsx
│   │   ├── missions/[id]/page.tsx
│   │   ├── memory/page.tsx        # Memory Inspector
│   │   ├── reflections/page.tsx   # Reflection Feed
│   │   ├── agents/page.tsx        # Skill registry view + peer-search
│   │   ├── replay/[traceId]/page.tsx
│   │   ├── analytics/page.tsx
│   │   └── settings/page.tsx
│   └── api/                    # Route handlers (proxy + auth callbacks)
│       ├── auth/[...nextauth]/route.ts
│       ├── livekit-token/route.ts          # thin proxy to FastAPI
│       └── proxy/[...path]/route.ts        # generic stream-preserving proxy
├── components/
│   ├── nav/Sidebar.tsx
│   ├── nav/Topbar.tsx
│   ├── voice/VoiceConsole.tsx
│   ├── voice/Waveform.tsx
│   ├── voice/TranscriptStream.tsx
│   ├── voice/ModeToggle.tsx
│   ├── map/MapView.tsx
│   ├── map/NoFlyLayer.tsx
│   ├── map/DroneMarker.tsx
│   ├── map/FacilityCluster.tsx
│   ├── map/ArcTrails.tsx              # deck.gl overlay
│   ├── scene/DroneScene.tsx           # react-three-fiber
│   ├── mission/MissionCard.tsx
│   ├── mission/RouteTimeline.tsx
│   ├── mission/PayloadStatus.tsx
│   ├── mission/RiskBadge.tsx
│   ├── mission/DispatchForm.tsx
│   ├── memory/MemoryInspector.tsx
│   ├── memory/MemoryCard.tsx
│   ├── memory/ReflectionFeed.tsx
│   ├── memory/SkillCard.tsx
│   ├── analytics/SelfEvolutionChart.tsx
│   ├── analytics/MissionComparison.tsx
│   ├── demo/DemoMenu.tsx
│   └── ui/                       # shadcn primitives
│       ├── button.tsx
│       ├── card.tsx
│       ├── dialog.tsx
│       ├── sheet.tsx
│       ├── badge.tsx
│       ├── tooltip.tsx
│       ├── select.tsx
│       ├── command.tsx
│       ├── skeleton.tsx
│       └── sonner.tsx
├── lib/
│   ├── api.ts            # typed FastAPI client (Server Actions where possible)
│   ├── ws.ts             # mission/dashboard sockets
│   ├── sse.ts            # agents/stream SSE
│   ├── livekit.ts        # token fetch + room helpers
│   ├── mongo-realtime.ts # higher-level subscribe(filter) helper
│   ├── auth.ts           # NextAuth config
│   ├── env.ts            # zod-validated env
│   └── format.ts
└── styles/globals.css
```

---

## 2 · Design tokens — `styles/globals.css`

The whole palette, radii, shadows, motion live in one place. Tailwind v4 picks them up via the `@theme` block.

```css
/* web/styles/globals.css */
@import "tailwindcss";
@import "tw-animate-css";

@theme {
  /* ---------- light surfaces ---------- */
  --color-canvas:        #FAFAFA;            /* app shell background */
  --color-surface:       #FFFFFF;            /* cards, sheets */
  --color-surface-2:     #F5F7FA;            /* sub-cards, list rows */
  --color-elevated:      #FFFFFF;            /* dialogs, popovers */

  /* ---------- text ---------- */
  --color-fg:            #0F172A;            /* slate-900 */
  --color-fg-muted:      #475569;            /* slate-600 */
  --color-fg-subtle:     #94A3B8;            /* slate-400 */
  --color-fg-inverse:    #FFFFFF;

  /* ---------- borders ---------- */
  --color-border:        #E2E8F0;            /* slate-200 hairline */
  --color-border-strong: #CBD5E1;            /* slate-300 */

  /* ---------- accent ---------- */
  --color-accent:        #4F46E5;            /* indigo-600 */
  --color-accent-soft:   #EEF2FF;            /* indigo-50 */
  --color-accent-fg:     #312E81;            /* indigo-900 */

  /* ---------- semantic ---------- */
  --color-success:       #10B981;            /* emerald-500 */
  --color-success-soft:  #ECFDF5;
  --color-warning:       #D97706;            /* amber-600 */
  --color-warning-soft:  #FFFBEB;
  --color-danger:        #DC2626;            /* medical red */
  --color-danger-soft:   #FEF2F2;
  --color-info:          #0284C7;
  --color-info-soft:     #F0F9FF;

  /* ---------- typography ---------- */
  --font-sans: "Geist Sans", "Inter", ui-sans-serif, system-ui;
  --font-mono: "Geist Mono", "JetBrains Mono", ui-monospace;
  --tracking-tight: -0.011em;

  /* ---------- radii ---------- */
  --radius-xs: 0.25rem;
  --radius-sm: 0.375rem;
  --radius-md: 0.625rem;
  --radius-lg: 0.875rem;
  --radius-xl: 1.25rem;
  --radius-pill: 999px;

  /* ---------- elevation (subtle, no neobrutalist heaviness) ---------- */
  --shadow-1: 0 1px 1px rgba(15,23,42,0.04), 0 1px 2px rgba(15,23,42,0.04);
  --shadow-2: 0 1px 2px rgba(15,23,42,0.05), 0 4px 12px rgba(15,23,42,0.04);
  --shadow-3: 0 4px 8px rgba(15,23,42,0.06), 0 12px 32px rgba(15,23,42,0.08);
  --shadow-focus: 0 0 0 3px rgba(79,70,229,0.20);

  /* ---------- motion presets ---------- */
  --ease-out-soft: cubic-bezier(0.22, 1, 0.36, 1);
  --duration-quick: 120ms;
  --duration-base: 220ms;
  --duration-slow: 380ms;
}

@layer base {
  html, body { background: var(--color-canvas); color: var(--color-fg); font-family: var(--font-sans); letter-spacing: var(--tracking-tight); }
  *:focus-visible { outline: none; box-shadow: var(--shadow-focus); border-radius: var(--radius-sm); }
  ::selection { background: var(--color-accent-soft); color: var(--color-accent-fg); }
  hr { border-color: var(--color-border); }
}

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
}
```

`tailwind.config.ts` is intentionally tiny — it just lists `content` paths so Tailwind v4 scans them.

---

## 3 · App shell — `app/(app)/layout.tsx`

```tsx
// web/app/(app)/layout.tsx
import { ReactNode } from "react";
import { Sidebar } from "@/components/nav/Sidebar";
import { Topbar } from "@/components/nav/Topbar";
import { Toaster } from "@/components/ui/sonner";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid h-dvh grid-cols-[280px_1fr] grid-rows-[56px_1fr] bg-canvas text-fg">
      <header className="col-span-2 row-start-1 border-b border-border bg-surface">
        <Topbar />
      </header>
      <aside className="row-start-2 border-r border-border bg-surface">
        <Sidebar />
      </aside>
      <main className="row-start-2 col-start-2 overflow-auto p-6">
        {children}
      </main>
      <Toaster richColors position="top-right" />
    </div>
  );
}
```

`Sidebar` exposes: Dashboard · Dispatch · Missions · Memory · Reflections · Agents · Analytics · Settings · **Demo** (separator). `Topbar` shows operator avatar, mission count badge (live), and the `<VoiceConsole/>` "join room" button.

---

## 4 · Real-time wiring — `lib/`

### 4.1 `lib/env.ts`

```ts
import { z } from "zod";
const env = z.object({
  NEXT_PUBLIC_API_BASE: z.string().url(),
  NEXT_PUBLIC_WS_BASE: z.string().url().optional(),
  NEXT_PUBLIC_LIVEKIT_URL: z.string().url(),
}).parse(process.env);
export default env;
```

### 4.2 `lib/api.ts`

Typed wrapper around `fetch`. Server Actions for mutations where possible; `fetchStream` returns an async iterator over SSE events.

```ts
// web/lib/api.ts
import env from "./env";
import type { Mission, Drone, Facility, MemoryHit } from "./types";

const base = env.NEXT_PUBLIC_API_BASE;

async function authedFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  // session token injected by Next route handler (api/proxy)
  const r = await fetch(`${base}${path}`, { ...init, headers, cache: "no-store" });
  if (!r.ok) throw new APIError(r.status, await r.text());
  return r;
}

export async function listMissions(): Promise<Mission[]> {
  return (await authedFetch("/api/missions")).json();
}

export async function getMission(id: string): Promise<{ mission: Mission; deliveries: any[]; flight_logs: any[] }> {
  return (await authedFetch(`/api/missions/${id}`)).json();
}

export async function createMission(payload: any) {
  return (await authedFetch("/api/missions", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: { "Idempotency-Key": crypto.randomUUID() },
  })).json();
}

export async function memorySearch(query: string, k = 5, filters?: any): Promise<{ hits: MemoryHit[] }> {
  return (await authedFetch("/api/memory/search", {
    method: "POST", body: JSON.stringify({ query, k, filters }),
  })).json();
}

export async function* fetchSSE(path: string): AsyncIterable<{ event: string; data: any }> {
  const r = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!r.body) return;
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const ev = /event:\s*(.+)/.exec(chunk)?.[1] ?? "message";
      const data = /data:\s*(.+)/.exec(chunk)?.[1] ?? "{}";
      yield { event: ev, data: JSON.parse(data) };
    }
  }
}

export class APIError extends Error {
  constructor(public status: number, public body: string) { super(`api ${status}: ${body}`); }
}
```

### 4.3 `lib/ws.ts` — typed WS client with auto-reconnect

```ts
// web/lib/ws.ts
import env from "./env";
type Msg = { kind: string; doc?: any; op?: string; payload?: any; id?: string };

export interface MissionSocket {
  on(kind: "telemetry" | "flight_log" | "mission_update", cb: (doc: any) => void): () => void;
  ack(id: string): void;
  close(): void;
}

export function openMissionSocket(missionId: string, token: string): MissionSocket {
  const url = (env.NEXT_PUBLIC_WS_BASE ?? env.NEXT_PUBLIC_API_BASE.replace(/^http/, "ws"))
    + `/ws/missions/${missionId}?token=${token}`;
  let ws: WebSocket | null = null;
  let backoff = 500;
  const handlers = new Map<string, Set<(doc: any) => void>>();

  function connect() {
    ws = new WebSocket(url);
    ws.onopen = () => { backoff = 500; };
    ws.onmessage = (e) => {
      const m: Msg = JSON.parse(e.data);
      handlers.get(m.kind)?.forEach((cb) => cb(m.doc ?? m.payload));
      if (m.id) ws?.send(JSON.stringify({ kind: "ack", id: m.id }));
    };
    ws.onclose = () => {
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 10_000);
    };
  }
  connect();
  return {
    on(kind, cb) {
      let set = handlers.get(kind); if (!set) handlers.set(kind, set = new Set());
      set.add(cb); return () => set!.delete(cb);
    },
    ack(id) { ws?.send(JSON.stringify({ kind: "ack", id })); },
    close() { ws?.close(); },
  };
}
```

### 4.4 `lib/sse.ts`

```ts
// web/lib/sse.ts
import env from "./env";
export function openAgentsStream(filters: { kind?: string; mission_id?: string; operator_id?: string },
                                 onMessage: (doc: any) => void) {
  const qs = new URLSearchParams(filters as any).toString();
  const es = new EventSource(`${env.NEXT_PUBLIC_API_BASE}/api/agents/stream?${qs}`);
  es.addEventListener("message", (e) => onMessage(JSON.parse(e.data)));
  return () => es.close();
}
```

### 4.5 `lib/livekit.ts`

```ts
// web/lib/livekit.ts
import env from "./env";
import { Room, RoomEvent, ConnectionState, type RoomOptions } from "livekit-client";

export interface LkSession { url: string; token: string; room: string; identity: string; }

export async function fetchLiveKitToken(opts: { mode: "ptt" | "always_on"; language: "en"|"auto"; missionId?: string }): Promise<LkSession> {
  const r = await fetch("/api/livekit-token", { method: "POST", body: JSON.stringify(opts) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function createRoom(): Room {
  const opts: RoomOptions = {
    adaptiveStream: true,
    dynacast: true,
    publishDefaults: { audioPreset: { maxBitrate: 32_000, dtx: true } },
  };
  return new Room(opts);
}

export async function publishData(room: Room, data: object) {
  await room.localParticipant.publishData(new TextEncoder().encode(JSON.stringify(data)), { reliable: true });
}
```

---

## 5 · Component specs

For each non-trivial component: **props · behaviour · states (loading/empty/error) · data sources · a11y notes.**

### 5.1 `<VoiceConsole/>`

**Props.** `{ missionId?: string; defaultMode?: "ptt"|"always_on"; defaultLanguage?: "en"|"auto"; }`

**Behaviour.** Mounts a `LiveKitRoom`, joins, renders `<RoomAudioRenderer/>` so the operator hears narration. Renders the `<Waveform/>` for incoming TTS audio. Renders `<TranscriptStream/>` (subscribes to `agents/stream` filtered by `kind in ['user','supervisor','narrator','signature']`). Footer holds: PTT button (`onMouseDown`/`onTouchStart` publishes `{ ptt: true }`, `onMouseUp` `{ ptt: false }`), mode toggle, language select, and a "Text mode" toggle that swaps to an input box that hits `/api/chat`.

**States.** `connecting`, `connected`, `reconnecting`, `disconnected`, `text-mode`. Each renders an unmistakable colour chip in the corner.

**Data sources.** `/api/livekit/token`, `/api/agents/stream`. Data channel inbound: `{ toast }` → `sonner.toast`.

**A11y.** PTT button is `<button aria-pressed>`. `<TranscriptStream/>` is a polite live region (`aria-live="polite"`). Keyboard shortcut `Space` for PTT (announced in tooltip). Keyboard `Esc` mutes mic.

```tsx
// web/components/voice/VoiceConsole.tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { Room } from "livekit-client";
import { fetchLiveKitToken, publishData } from "@/lib/livekit";
import { Waveform } from "./Waveform";
import { TranscriptStream } from "./TranscriptStream";
import { ModeToggle } from "./ModeToggle";
import { Mic, MicOff, Wifi, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type Mode = "ptt" | "always_on";

export function VoiceConsole({ missionId, defaultMode = "always_on", defaultLanguage = "en" }: {
  missionId?: string; defaultMode?: Mode; defaultLanguage?: "en"|"auto";
}) {
  const [token, setToken] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [language, setLanguage] = useState<"en"|"auto">(defaultLanguage);
  const [textMode, setTextMode] = useState(false);
  const roomRef = useRef<Room | null>(null);

  useEffect(() => {
    fetchLiveKitToken({ mode, language, missionId }).then((s) => {
      setToken(s.token); setUrl(s.url);
    }).catch((e) => toast.error(`Voice room failed: ${e.message}`));
  }, [mode, language, missionId]);

  if (textMode) return <TextModeFallback onExit={() => setTextMode(false)} />;
  if (!token || !url) return <VoiceSkeleton />;

  return (
    <LiveKitRoom serverUrl={url} token={token} connect audio video={false}
                 onConnected={() => toast.success("Voice channel ready")}
                 onDisconnected={() => toast.warning("Voice channel disconnected")}
                 onMediaDeviceFailure={() => toast.error("Microphone blocked")}
                 data-channel-callback={(payload) => {
                   try {
                     const msg = JSON.parse(new TextDecoder().decode(payload));
                     if (msg.toast) toast[msg.toast.level as "info"|"error"](msg.toast.msg);
                   } catch {}
                 }}>
      <RoomAudioRenderer />
      <div className="flex items-center gap-3 rounded-md border border-border bg-surface p-3 shadow-1">
        <div className="flex items-center gap-2">
          <Wifi className="h-4 w-4 text-success" />
          <Badge variant="outline">{mode === "ptt" ? "Push to talk" : "Always on"}</Badge>
        </div>
        <Waveform />
        <div className="ml-auto flex items-center gap-2">
          <ModeToggle mode={mode} onChange={async (m) => {
            setMode(m); if (roomRef.current) await publishData(roomRef.current, { mode: m });
          }} />
          <Button variant="ghost" size="sm" onClick={() => setTextMode(true)}>Text mode</Button>
          {mode === "ptt" && (
            <PttButton onDown={() => roomRef.current && publishData(roomRef.current, { ptt: true })}
                       onUp={() => roomRef.current && publishData(roomRef.current, { ptt: false })} />
          )}
        </div>
      </div>
      <TranscriptStream missionId={missionId} />
    </LiveKitRoom>
  );
}

function PttButton({ onDown, onUp }: { onDown: () => void; onUp: () => void }) {
  const [active, setActive] = useState(false);
  return (
    <Button aria-pressed={active}
            onMouseDown={() => { setActive(true); onDown(); }}
            onMouseUp={() => { setActive(false); onUp(); }}
            onMouseLeave={() => active && (setActive(false), onUp())}
            className={active ? "bg-danger text-fg-inverse" : ""}>
      {active ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}<span className="ml-2">Hold to talk</span>
    </Button>
  );
}

function VoiceSkeleton() { return <div className="h-14 animate-pulse rounded-md bg-surface-2" />; }
function TextModeFallback({ onExit }: { onExit: () => void }) { /* SSE chat — see §5.2 */ return null; }
```

### 5.2 `<TranscriptStream/>`

Subscribes to `openAgentsStream({kind: undefined, mission_id})`. Each message renders as a bubble with author chip (`Operator`, `Mission Control`, `Narrator`, `Signature`). Auto-scrolls to bottom unless the user has scrolled up (sticky-bottom pattern). Animates new bubbles via `framer-motion`'s `AnimatePresence` with a 180 ms `--ease-out-soft` slide.

**Empty.** "*Standing by. Say something to dispatch.*"
**Loading.** Skeleton with three 40 px rows.
**Error.** Inline retry button; toast.

### 5.3 `<Waveform/>`

Subscribes to the active room's audio Track. Uses `Track.attach` to get an HTMLAudioElement, then `AudioContext.createMediaElementSource(...)` → `AnalyserNode` → 32-bin frequency draw on a `<canvas>`. 60 fps with `requestAnimationFrame`. Honours `prefers-reduced-motion` by drawing a static centred bar.

### 5.4 Toaster + data-channel bridge

`<Toaster/>` from shadcn-sonner; data-channel callback in `<VoiceConsole/>` calls `toast.error/info/success`. The Worker uses `push_toast(ctx, level, msg)` (file 06 §10).

### 5.5 `<MapView/>` — Leaflet + deck.gl

**Props.** `{ missionId?: string; height?: number; showNoFly?: boolean; showFacilities?: boolean; followDrone?: string; }`

**Layers (z-order, bottom up).** OSM tiles (Carto Positron — light, low chroma) → `<NoFlyLayer/>` (semi-transparent red polygons, 0.20 opacity, 1 px stroke `--color-danger`) → `<FacilityCluster/>` (Leaflet.markercluster; hospital icons in indigo) → animated `ArcLayer` from deck.gl (`<ArcTrails/>`) → `<DroneMarker/>` (rotated by heading).

**Behaviour.** WS subscribes to `/ws/missions/{id}` for `telemetry`. Each tick updates the marker's `position` and `headingDeg`; arc progress is interpolated from `progress = elapsed / planned_time_s`. `followDrone` keeps the camera centred via `map.panTo` with a 50 ms throttle.

**States.** `loading` (skeleton over the map area), `error` (banner with retry; map still renders base tiles).

**Data sources.** `GET /api/no-fly-zones?bbox=...`, `GET /api/facilities?near=...`, `WS /ws/missions/{id}`.

**A11y.** Map is `role="application"` with keyboard pan/zoom hints in a hidden description.

```tsx
// web/components/map/MapView.tsx
"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { NoFlyLayer } from "./NoFlyLayer";
import { FacilityCluster } from "./FacilityCluster";
import { DroneMarker } from "./DroneMarker";
import { openMissionSocket } from "@/lib/ws";

const ArcTrails = dynamic(() => import("./ArcTrails").then(m => m.ArcTrails), { ssr: false });

export function MapView({ missionId, height = 480, showNoFly = true, showFacilities = true, followDrone }: any) {
  const [drones, setDrones] = useState<Record<string, any>>({});
  useEffect(() => {
    if (!missionId) return;
    const sock = openMissionSocket(missionId, ""); // token from cookie via proxy
    const off = sock.on("telemetry", (d) => setDrones((s) => ({ ...s, [d.drone_id]: d })));
    return () => { off(); sock.close(); };
  }, [missionId]);

  return (
    <div className="overflow-hidden rounded-lg border border-border shadow-1" style={{ height }}>
      <MapContainer center={[51.515, -0.072]} zoom={12} className="h-full w-full" zoomControl={false}>
        <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png" attribution="© OSM · Carto" />
        {showNoFly && <NoFlyLayer />}
        {showFacilities && <FacilityCluster />}
        <ArcTrails missionId={missionId} />
        {Object.values(drones).map((d: any) => <DroneMarker key={d.drone_id} drone={d} />)}
        {followDrone && drones[followDrone] && <Recenter to={drones[followDrone].position} />}
      </MapContainer>
    </div>
  );
}

function Recenter({ to }: { to: [number, number] }) {
  const map = useMap();
  useEffect(() => { map.panTo(to, { animate: true, duration: 0.3 }); }, [to[0], to[1]]);
  return null;
}
```

### 5.6 `<NoFlyLayer/>`

Fetches `/api/no-fly-zones?bbox=` keyed on viewport. Renders a Leaflet `Polygon` per geometry with `fillColor="var(--color-danger)"`, `fillOpacity=0.18`, `weight=1`, `color="var(--color-danger)"`. Tooltip on hover with name + severity.

### 5.7 `<DroneMarker/>`

Uses `L.divIcon` so we can include an SVG drone rotated by `transform: rotate(${heading}deg)`. Pulses (`framer-motion`) every 2 s when `status==="in_transit"`. Click opens a popover with battery, alt, payload temp, current waypoint.

### 5.8 `<ArcTrails/>` (deck.gl)

Wraps a `DeckGL` overlay synced to the Leaflet viewport via `react-leaflet`'s `useMap()` and `MapboxOverlay` adapter. Layer: `ArcLayer` with `getSourcePosition`, `getTargetPosition`, `getSourceColor=[16,185,129,200]` (success), `getTargetColor=[79,70,229,200]` (accent), `getWidth=3`, animated by progress via `getTilt: d => d.progress * 30`. Source data is the mission's `route` array; the *current* arc to next waypoint blends progress.

### 5.9 `<DroneScene/>` (react-three-fiber)

**Props.** `{ droneState: TelemetryFrame; followCamera?: boolean; }`

Components: `<Sky/>` from drei, ground `<Grid/>` (1 m × 1 m, tinted slate-200), a single GLTF drone (`useGLTF("/models/drone.glb")`) translated/rotated from telemetry. `<OrbitControls makeDefault/>` unless `followCamera` is on, in which case a small `useFrame` lerps the camera behind the drone.

**Performance.** `dynamic(() => import("./DroneScene"), { ssr: false })`. Frame loop only runs while the page is visible (`useFrame` inside `<RenderInBackground/>` is gated by `document.visibilityState`).

### 5.10 `<MemoryInspector/>`

**Props.** `{ operatorQuery?: string; missionId?: string; }`

**Layout.**

```
┌─ left rail (320 px) ──────────┬─ main (1fr) ─────────┬─ right rail (320 px) ─┐
│ Current operator query        │ Cards list             │ "Why these were      │
│ (textarea, debounce 250 ms)   │ (vertical, 12 px gap)  │  chosen" — the       │
│ Filters: kind, region, k=5    │ Each: kind icon, snip, │  RetrievalCriticAgent│
│                               │ chips (region/weather),│  criticism + scores  │
│                               │ score bar              │                      │
└───────────────────────────────┴────────────────────────┴──────────────────────┘
```

Each card click opens a `<Sheet/>` (right side) with the full Mongo doc, the full embedding query, and a per-hop trace.

**Data.** `POST /api/memory/search` for the cards. SSE `/api/agents/stream?kind=memory_query&mission_id=...` to stream new retrievals as the planner runs. SSE `/api/agents/stream?kind=retrieval_critic` for the right-rail criticism.

**States.** `idle` ("Type a query to inspect memory"), `loading` (skeleton cards × 3), `empty` ("No memories matched — try broader filters").

**A11y.** Cards are `<article role="button" tabIndex={0}>`. Score bar has `aria-label="similarity 0.83"`.

```tsx
// web/components/memory/MemoryCard.tsx
import { Badge } from "@/components/ui/badge";
import { motion } from "framer-motion";
import { Brain, ShieldAlert, Hospital, Cloud, UserRound } from "lucide-react";

const ICONS: Record<string, any> = {
  reflection: Brain, incident: ShieldAlert, regulation: ShieldAlert,
  facility_intel: Hospital, weather_class: Cloud, operator_pref: UserRound,
};

export function MemoryCard({ hit, onOpen }: { hit: any; onOpen: () => void }) {
  const Icon = ICONS[hit.kind] ?? Brain;
  return (
    <motion.article role="button" tabIndex={0} onClick={onOpen}
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}
      className="cursor-pointer rounded-md border border-border bg-surface p-4 shadow-1 hover:shadow-2">
      <header className="mb-2 flex items-center gap-2">
        <Icon className="h-4 w-4 text-accent" />
        <span className="text-xs uppercase tracking-wide text-fg-muted">{hit.kind}</span>
        <span className="ml-auto font-mono text-xs text-fg-muted">{hit.score.toFixed(3)}</span>
      </header>
      <p className="line-clamp-3 text-sm text-fg">{hit.text}</p>
      <footer className="mt-3 flex flex-wrap gap-1.5">
        {hit.metadata?.region && <Badge variant="outline">{hit.metadata.region}</Badge>}
        {hit.metadata?.weather_class && <Badge variant="outline">{hit.metadata.weather_class}</Badge>}
        {hit.metadata?.success !== undefined && (
          <Badge className={hit.metadata.success ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}>
            {hit.metadata.success ? "succeeded" : "failed"}
          </Badge>
        )}
      </footer>
      <div className="mt-3 h-1 rounded bg-surface-2" aria-label={`similarity ${hit.score.toFixed(2)}`}>
        <div className="h-1 rounded bg-accent" style={{ width: `${Math.round(hit.score * 100)}%` }} />
      </div>
    </motion.article>
  );
}
```

### 5.11 `<ReflectionFeed/>`

Vertical timeline. Each item: timestamp (relative), kind chip, lesson text, mission link. New lessons slide in from the top with a soft pulse (`box-shadow` from `var(--shadow-2)` to `var(--shadow-1)` over 1.2 s).

**Data.** SSE `/api/agents/stream?kind=reflection`. Filter chips along the top: `reflection · incident · regulation · facility_intel · operator_pref`.

**Empty.** "*No lessons yet. Run a mission and the system will start learning.*"

### 5.12 `<SkillCard/>` & Agents page

Lists skills from the registry. Search box hits `POST /api/skills/peer-search`. Each skill renders: name, summary, parameters, average win-rate badge, link to source.

### 5.13 `<SelfEvolutionChart/>`

Recharts `LineChart` of `actual_time_s` per `take_n` per scenario. Axes: x=`take_n`, y=`actual_time_s`. One line per scenario, coloured from the accent palette. Annotation markers (`ReferenceDot`) when a new lesson causes an inflection (detected backend-side: lesson timestamp falls between take_{n-1} and take_n).

**Data.** `GET /api/analytics/self-evolution?scenarios=...` (defined in file 07 alongside other analytics). Refreshes via SWR-style polling every 10 s plus one push from SSE on `kind=reflection`.

```tsx
// web/components/analytics/SelfEvolutionChart.tsx
"use client";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceDot } from "recharts";

export function SelfEvolutionChart({ data }: { data: { take_n: number; scenario: string; actual_time_s: number; lesson?: string }[] }) {
  const scenarios = Array.from(new Set(data.map(d => d.scenario)));
  const colors = ["#4F46E5","#10B981","#DC2626","#0284C7","#D97706"];
  return (
    <div className="h-[320px] w-full rounded-md border border-border bg-surface p-4 shadow-1">
      <ResponsiveContainer>
        <LineChart data={data}>
          <XAxis dataKey="take_n" tick={{ fontSize: 12, fill: "#475569" }} />
          <YAxis tick={{ fontSize: 12, fill: "#475569" }} unit="s" />
          <Tooltip />
          {scenarios.map((s, i) => (
            <Line key={s} type="monotone" dataKey="actual_time_s"
                  data={data.filter(d => d.scenario === s)}
                  stroke={colors[i % colors.length]} strokeWidth={2}
                  dot={{ r: 3 }} activeDot={{ r: 5 }} name={s} />
          ))}
          {data.filter(d => d.lesson).map((d, i) => (
            <ReferenceDot key={i} x={d.take_n} y={d.actual_time_s} r={6}
                          fill="#10B981" stroke="#FFFFFF" strokeWidth={2}
                          ifOverflow="visible" />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### 5.14 `<MissionComparison/>`

Three-bar chart (drone · helicopter · ambulance) for time, cost, CO₂. Uses recharts `BarChart`. Data fetched via `GET /api/missions/{id}/comparison`.

### 5.15 `<DispatchForm/>`

Multi-row form for batch deliveries. Address autocomplete via `GET /api/facilities?q=` (Atlas Search). On submit, calls `createMission(...)` Server Action; on success, `router.push('/missions/' + id)`. Optimistic UI: a placeholder MissionCard appears immediately, replaced by the real one when the WS fires `mission_update`.

### 5.16 `<MissionCard/>` & `<RouteTimeline/>`

`MissionCard` lists key facts (status badge, drone id, ETA, payload temp). `RouteTimeline` is a horizontal timeline of waypoints with progress; each waypoint has tooltip with arrival time + handover info. WS-driven updates via `openMissionSocket`.

### 5.17 `<DemoMenu/>`

In the sidebar's footer. Buttons: `Inject Storm` (POST `/api/simulate-weather`), `Inject Obstacle` (POST `/api/internal/inject-obstacle` — admin), `Replay Mission` (opens command palette with mission selector), `Run Encore` (re-runs the last mission with `take_n+1`). Each shows a confirm `Dialog` for safety. Triggers a `sonner` confirmation on success.

---

## 6 · Page-level wiring

### 6.1 `/dashboard`

Server Component: `Promise.all([listMissions(), listDrones()])` then renders a 12-col grid: top row = active mission count + drones-online + reroutes-today + reflections-today. Middle row: `<MapView/>` (8 cols) + `<VoiceConsole/>` (4 cols). Bottom row: `<MissionList/>` + `<ReflectionFeedPreview limit={5}/>`. The list updates via `WS /ws/dashboard`.

### 6.2 `/missions/[id]`

Server-side `getMission(id)` for initial render (Suspense boundary). Client subtrees:

- `<MapView missionId={id} followDrone={...}/>`
- `<DroneScene/>` (toggleable card)
- `<RouteTimeline mission={mission}/>`
- `<PayloadStatus deliveryIds={...}/>`
- `<RiskBadge missionId={id}/>` — server fetched then refreshed on WS `mission_update`
- `<MemoryInspector missionId={id}/>` (collapsible)
- `<TranscriptStream missionId={id}/>` (when room joined)

### 6.3 `/memory`

Pure client. The `<MemoryInspector/>` takes the full screen; left rail lets you scrub through prior `memory_query` events captured per session.

### 6.4 `/reflections`

`<ReflectionFeed/>` full-bleed; filter chips at top.

### 6.5 `/agents`

Two columns: skill grid (search-driven via peer-search) on the left; on the right, a live "agent activity" stream from SSE filtered by `kind=agent_activity`.

### 6.6 `/replay/[traceId]`

Pulls `/api/admin/trace/{traceId}` and renders a Gantt-style waterfall. Each span is clickable → opens a sheet with full meta. Used for post-mortem on demos.

### 6.7 `/analytics`

Header KPIs (today vs all-time), then `<SelfEvolutionChart/>`, then `<MissionComparison/>`. Data sourced from `/api/analytics/*`.

---

## 7 · Auth — `lib/auth.ts`

```ts
// web/lib/auth.ts
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import EmailProvider from "next-auth/providers/email";
import { MongoDBAdapter } from "@auth/mongodb-adapter";
import clientPromise from "./mongo-client";
import { sign } from "jsonwebtoken";

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: MongoDBAdapter(clientPromise, { databaseName: "dronefleet" }),
  session: { strategy: "jwt" },
  providers: [
    EmailProvider({ server: process.env.EMAIL_SERVER!, from: process.env.EMAIL_FROM! }),
    Credentials({
      credentials: { email: {}, password: {} },
      async authorize(creds) {
        const r = await fetch(`${process.env.API_BASE}/api/auth/login`, {
          method: "POST", body: JSON.stringify(creds),
        });
        if (!r.ok) return null;
        return r.json();
      }
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) { token.sub = user.id; token.role = (user as any).role; }
      return token;
    },
    async session({ session, token }) {
      // Mint a backend JWT signed with shared secret; frontend will pass it in Authorization
      session.backendToken = sign({ sub: token.sub, role: token.role }, process.env.JWT_SECRET!,
                                  { expiresIn: "1h", algorithm: "HS256" });
      return session;
    },
  },
});
```

The `app/api/proxy/[...path]/route.ts` route handler forwards browser requests to FastAPI, attaching `Authorization: Bearer ${session.backendToken}` server-side so the token never leaves the Node runtime. This avoids CORS+credentials headaches and prevents XSS leaking the backend JWT.

---

## 8 · Performance

- **RSC + Suspense.** Pages like `/missions/[id]` render the static shell from RSC, then stream the client-rendered map/scene below.
- **Streamed UI for chat.** The text-mode fallback (§5.1) uses `fetchSSE` and `useTransition` to render tokens as they arrive without blocking the page.
- **Dynamic imports.** `MapView`, `DroneScene`, `ArcTrails`, `MemoryInspector`'s sheet contents are all `dynamic(..., { ssr: false })`.
- **Bundle budget.** Sidebar route chunks ≤ 60 kB gzipped; `/missions/[id]` ≤ 220 kB gzipped (map + deck + three lazy-loaded after first paint).
- **WS coalescing.** `openMissionSocket` debounces telemetry ticks at 60 fps; the marker uses `requestAnimationFrame` to interpolate position.
- **Image budget.** OSM tiles cached aggressively (`Cache-Control: public, max-age=86400` via SW). One drone GLTF at 180 kB.

---

## 9 · Light-mode polish

- **Skeletons.** Every async surface has a sized skeleton matching its eventual layout — no layout shift.
- **Sonner.** Top-right; rich colours; success uses `--color-success`, error `--color-danger`, info `--color-info`.
- **Focus rings.** Global `:focus-visible` with `--shadow-focus`, indigo 20%-opacity halo.
- **Motion.** All transitions ≤ 220 ms; `--ease-out-soft`; `prefers-reduced-motion` collapses everything to 0.001 ms.
- **Text contrast.** All foreground/background pairs verified ≥ 4.5:1 with axe-core.
- **Hairlines.** Borders are 1 px `--color-border`; never a heavier weight unless emphasis demands it.
- **Empty states.** Always have a friendly sentence + a primary action — never a blank panel.

---

## 10 · Demo affordances

`<DemoMenu/>` exposes the four buttons. Each maps to a documented backend route and is gated behind `role="admin"` (set on the seeded demo operator).

```tsx
// web/components/demo/DemoMenu.tsx
"use client";
import { Button } from "@/components/ui/button";
import { Cloud, AlertTriangle, RotateCcw, Zap } from "lucide-react";
import { toast } from "sonner";

export function DemoMenu() {
  return (
    <div className="space-y-2 border-t border-border p-3">
      <p className="text-xs uppercase tracking-wide text-fg-muted">Demo</p>
      <Button variant="outline" className="w-full justify-start" onClick={async () => {
        const r = await fetch("/api/proxy/api/simulate-weather", { method: "POST",
          body: JSON.stringify({ location_id: "homerton", severity: "high" })});
        toast[r.ok ? "success" : "error"](r.ok ? "Storm injected" : "Failed");
      }}><Cloud className="mr-2 h-4 w-4" />Inject Storm</Button>
      <Button variant="outline" className="w-full justify-start" onClick={async () => {
        await fetch("/api/proxy/api/internal/inject-obstacle", { method: "POST",
          body: JSON.stringify({ kind: "crane", lat: 51.519, lon: -0.063 })});
        toast.success("Obstacle injected");
      }}><AlertTriangle className="mr-2 h-4 w-4" />Inject Obstacle</Button>
      <Button variant="outline" className="w-full justify-start"><RotateCcw className="mr-2 h-4 w-4" />Replay Mission</Button>
      <Button variant="outline" className="w-full justify-start"><Zap className="mr-2 h-4 w-4" />Run Encore</Button>
    </div>
  );
}
```

---

## 11 · Local dev

```bash
# from web/
pnpm install
pnpm dev          # next dev --turbo
# in another terminal
pnpm typecheck    # tsc --noEmit
pnpm lint         # next lint + eslint-plugin-import
pnpm test         # vitest
pnpm e2e          # playwright (smoke: dispatch a mission, see arc animate)
```

Required env (`.env.local`):

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_LIVEKIT_URL=wss://your-project.livekit.cloud
JWT_SECRET=<same as backend JWT_SECRET>
NEXTAUTH_SECRET=<random>
EMAIL_SERVER=smtp://...
EMAIL_FROM=ops@dronefleet.dev
MONGODB_URI=mongodb+srv://...
```

---

## 12 · Definition of Done

You ship the frontend when:

1. `pnpm build && pnpm start` boots cleanly with no TS errors and no runtime warnings in the console.
2. Lighthouse: Perf ≥ 92, A11y ≥ 100, Best Practices ≥ 100 on `/dashboard` (light only, throttled mobile).
3. The full demo from `REBUILD_PROMPT.md §8` runs end-to-end:
   - Operator joins the room → speaks → mission created → map animates → narrator narrates → reroute happens → memory cards appear → reflection card slides in → encore mission shows lower ETA on the chart.
4. All `<Suspense/>` boundaries render their skeleton fallback, never a flash of unstyled content.
5. `prefers-reduced-motion: reduce` removes every animation but the data stays correct.
6. Every backend route in [`07-backend-fastapi.md §3`](./07-backend-fastapi.md#3-route-inventory) has at least one consumer in the UI or an explicit decision logged in `docs/frontend-coverage.md`.

When all six tick, the operator console is judge-ready.
