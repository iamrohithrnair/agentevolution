/**
 * Mock backend — implements the REST + WS + SSE contract from
 * prompts/07-backend-fastapi.md so the frontend can ship and demo end-to-end
 * before the real FastAPI service lands (Phase 5 cloud handoff B).
 *
 * The simulator is deterministic-enough to be useful in Playwright while
 * remaining lively — drones traverse routes, telemetry ticks every 500 ms,
 * the planner cascade fan-outs over agents, and reflections drop after a
 * mission completes.  Everything is published on a tiny pub/sub bus so
 * `lib/ws.ts` and `lib/sse.ts` can fan it out to subscribers.
 */

import type {
  AgentMessage,
  AgentMessageKind,
  Delivery,
  Drone,
  ExperimentPoint,
  Facility,
  FlightLog,
  LngLat,
  MemoryHit,
  Mission,
  NoFlyZone,
  Skill,
  Supply,
  TelemetryFrame,
  Waypoint,
} from "./types";
import { bearingDeg, haversineMeters } from "./format";

// ─────────────────────────────────────────────────────────────────────────────
//  Tiny pub/sub bus — kept private to this module
// ─────────────────────────────────────────────────────────────────────────────

type BusEvent =
  | { type: "telemetry"; frame: TelemetryFrame }
  | { type: "flight_log"; log: FlightLog }
  | { type: "mission_update"; mission: Mission }
  | { type: "drone_update"; drone: Drone }
  | { type: "agent_message"; message: AgentMessage };

type Listener = (e: BusEvent) => void;

class Bus {
  private listeners = new Set<Listener>();
  on(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  emit(e: BusEvent): void {
    for (const fn of this.listeners) {
      try {
        fn(e);
      } catch {
        /* swallow listener errors so one bad subscriber doesn't kill the bus */
      }
    }
  }
}

const bus = new Bus();
export function onMockEvent(fn: Listener): () => void {
  return bus.on(fn);
}

function nextId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Seed data (East London medical-logistics scenario from prompts/00-overview)
// ─────────────────────────────────────────────────────────────────────────────

const FACILITIES: Facility[] = [
  {
    id: "fac_homerton",
    name: "Homerton University Hospital",
    type: "hospital",
    region: "Hackney",
    address: "Homerton Row, London E9 6SR",
    position: [-0.0428, 51.5505],
    capabilities: ["A&E", "trauma", "blood_bank"],
  },
  {
    id: "fac_royal_london",
    name: "Royal London Hospital",
    type: "hospital",
    region: "Whitechapel",
    address: "Whitechapel Rd, London E1 1FR",
    position: [-0.0594, 51.5188],
    capabilities: ["A&E", "trauma", "neonatal"],
  },
  {
    id: "fac_barts",
    name: "St Bartholomew's Hospital",
    type: "hospital",
    region: "City of London",
    address: "W Smithfield, London EC1A 7BE",
    position: [-0.1011, 51.5176],
    capabilities: ["cardiac", "oncology"],
  },
  {
    id: "fac_uclh",
    name: "University College Hospital",
    type: "hospital",
    region: "Bloomsbury",
    address: "235 Euston Rd, London NW1 2BU",
    position: [-0.1349, 51.5246],
    capabilities: ["A&E", "stroke"],
  },
  {
    id: "fac_kings",
    name: "King's College Hospital",
    type: "hospital",
    region: "Denmark Hill",
    address: "Denmark Hill, London SE5 9RS",
    position: [-0.0935, 51.4684],
    capabilities: ["liver", "trauma"],
  },
  {
    id: "fac_guys",
    name: "Guy's Hospital",
    type: "hospital",
    region: "London Bridge",
    address: "Great Maze Pond, London SE1 9RT",
    position: [-0.0871, 51.5039],
    capabilities: ["oncology", "dental"],
  },
  {
    id: "fac_blood_colindale",
    name: "NHS Blood & Transplant — Colindale",
    type: "blood_bank",
    region: "Colindale",
    address: "Charcot Rd, London NW9 5BG",
    position: [-0.2467, 51.5959],
    capabilities: ["o_neg", "o_pos", "platelets"],
  },
  {
    id: "fac_depot_canary",
    name: "Dronan Depot — Canary Wharf",
    type: "depot",
    region: "Canary Wharf",
    address: "Cabot Square, London E14 4QJ",
    position: [-0.0235, 51.5054],
    capabilities: ["fast_charge", "service"],
  },
  {
    id: "fac_pharmacy_dalston",
    name: "Dalston Community Pharmacy",
    type: "pharmacy",
    region: "Dalston",
    address: "Kingsland High St, London E8 2NS",
    position: [-0.0758, 51.5454],
    capabilities: ["insulin", "vaccine"],
  },
];

export function getMockFacilities(): Facility[] {
  return FACILITIES;
}

const NO_FLY_ZONES: NoFlyZone[] = [
  {
    id: "nfz_city_airport",
    name: "London City Airport CTR",
    country: "GB",
    severity: "high",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [0.0353, 51.4961],
          [0.0817, 51.4961],
          [0.0817, 51.5226],
          [0.0353, 51.5226],
          [0.0353, 51.4961],
        ],
      ],
    },
  },
  {
    id: "nfz_buckingham",
    name: "Royal Parks Restricted",
    country: "GB",
    severity: "medium",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-0.1519, 51.4998],
          [-0.1336, 51.4998],
          [-0.1336, 51.5095],
          [-0.1519, 51.5095],
          [-0.1519, 51.4998],
        ],
      ],
    },
  },
  {
    id: "nfz_thames_barrier",
    name: "Thames Barrier Operations",
    country: "GB",
    severity: "medium",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [0.0285, 51.4936],
          [0.0455, 51.4936],
          [0.0455, 51.5036],
          [0.0285, 51.5036],
          [0.0285, 51.4936],
        ],
      ],
    },
  },
  {
    id: "nfz_olympic_park",
    name: "Olympic Park Event NOTAM",
    country: "GB",
    severity: "low",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-0.0212, 51.5374],
          [-0.0049, 51.5374],
          [-0.0049, 51.5494],
          [-0.0212, 51.5494],
          [-0.0212, 51.5374],
        ],
      ],
    },
  },
];

export function getMockNoFlyZones(): NoFlyZone[] {
  return NO_FLY_ZONES;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Drones (3 in service)
// ─────────────────────────────────────────────────────────────────────────────

let DRONES: Drone[] = [
  {
    id: "drn_alpha",
    status: "idle",
    battery: 96,
    position: [-0.0235, 51.5054],
    heading_deg: 12,
    current_mission_id: null,
    last_seen: Date.now(),
    payload_temp_c: null,
  },
  {
    id: "drn_bravo",
    status: "idle",
    battery: 88,
    position: [-0.0235, 51.5054],
    heading_deg: 90,
    current_mission_id: null,
    last_seen: Date.now(),
    payload_temp_c: null,
  },
  {
    id: "drn_charlie",
    status: "charging",
    battery: 64,
    position: [-0.0235, 51.5054],
    heading_deg: 270,
    current_mission_id: null,
    last_seen: Date.now(),
    payload_temp_c: null,
  },
];

export function getMockDrones(): Drone[] {
  return DRONES.map((d) => ({ ...d }));
}

// ─────────────────────────────────────────────────────────────────────────────
//  Missions, deliveries, telemetry simulation
// ─────────────────────────────────────────────────────────────────────────────

const MISSIONS = new Map<string, Mission>();
const DELIVERIES = new Map<string, Delivery>();
const FLIGHT_LOGS: FlightLog[] = [];
const AGENT_MESSAGES: AgentMessage[] = [];
const MEMORY: MemoryHit[] = seedMemory();

function seedMemory(): MemoryHit[] {
  const now = Date.now();
  return [
    {
      id: "mem_storm_homerton",
      kind: "weather_class",
      text: "Storm class III over Homerton — prefer northern corridor via Hackney Marshes.",
      score: 0.91,
      metadata: { region: "Hackney", weather_class: "storm_iii", success: true },
      created_at: now - 1000 * 60 * 60 * 24 * 4,
    },
    {
      id: "mem_kings_handover",
      kind: "facility_intel",
      text: "King's College has reduced helipad clearance Mon-Wed 14:00-16:00; route to north pad.",
      score: 0.87,
      metadata: { region: "Denmark Hill", success: true },
      created_at: now - 1000 * 60 * 60 * 24 * 8,
    },
    {
      id: "mem_o_neg_chain",
      kind: "regulation",
      text: "O-neg cold-chain breach if payload_temp_c > 6 °C for >120 s — abort and recall.",
      score: 0.83,
      metadata: { success: false },
      created_at: now - 1000 * 60 * 60 * 24 * 14,
    },
    {
      id: "mem_olympic_park_notam",
      kind: "incident",
      text: "Olympic Park NOTAM caused two reroutes last week; check active events before takeoff.",
      score: 0.79,
      metadata: { region: "Stratford" },
      created_at: now - 1000 * 60 * 60 * 24 * 5,
    },
    {
      id: "mem_pref_mission_control",
      kind: "operator_pref",
      text: "Operator Daniels prefers terse narration: 'reroute · waypoint · landing' only.",
      score: 0.74,
      metadata: { success: true },
      created_at: now - 1000 * 60 * 60 * 24 * 2,
    },
  ];
}

export function searchMockMemory(query: string, k = 5): MemoryHit[] {
  // Trivial relevance: lexical overlap nudges score, otherwise keep seed scores.
  const q = query.toLowerCase().trim();
  const scored = MEMORY.map((m) => {
    const tokens = q.split(/\s+/).filter(Boolean);
    const overlap = tokens.filter((t) => m.text.toLowerCase().includes(t)).length;
    const boost = q ? Math.min(0.12, overlap * 0.04) : 0;
    return { ...m, score: Math.min(0.99, m.score + boost) };
  });
  return scored.sort((a, b) => b.score - a.score).slice(0, k);
}

export function listMockReflections(): MemoryHit[] {
  return MEMORY.filter((m) => m.kind === "reflection" || m.kind === "incident")
    .sort((a, b) => b.created_at - a.created_at)
    .slice(0, 50);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Skills registry seed
// ─────────────────────────────────────────────────────────────────────────────

const SKILLS: Skill[] = [
  {
    skill_id: "skl_route_or_tools",
    name: "OR-Tools route optimisation",
    agent: "PlannerAgent",
    summary:
      "Solves vehicle-routing for batch deliveries with no-fly polygons + weather costs.",
    parameters: ["origin", "stops", "max_battery_pct", "no_fly_zones"],
    win_rate: 0.92,
    invocations: 184,
  },
  {
    skill_id: "skl_replan_storm",
    name: "Storm-aware reroute",
    agent: "ReplannerAgent",
    summary: "Rebuilds the active leg given a fresh storm polygon from Atlas Trigger.",
    parameters: ["mission_id", "avoid_geometry"],
    win_rate: 0.88,
    invocations: 73,
  },
  {
    skill_id: "skl_payload_drift",
    name: "Cold-chain drift estimator",
    agent: "PayloadAgent",
    summary: "Projects integrity given ambient temperature, sun load, and cargo mass.",
    parameters: ["mission_id", "delivery_id"],
    win_rate: 0.95,
    invocations: 211,
  },
  {
    skill_id: "skl_geofence_check",
    name: "Live geofence intersect",
    agent: "GeofenceAgent",
    summary: "$geoIntersects against active no_fly_zones along the planned route.",
    parameters: ["polyline"],
    win_rate: 0.99,
    invocations: 412,
  },
  {
    skill_id: "skl_voice_signature",
    name: "Voice-signature handover",
    agent: "Narrator",
    summary: "Captures recipient signature via LiveKit prompt-and-confirm.",
    parameters: ["delivery_id", "recipient_name"],
    win_rate: 0.81,
    invocations: 96,
  },
  {
    skill_id: "skl_memory_recall",
    name: "Mission memory recall",
    agent: "MemoryAgent",
    summary: "Voyage-3 embedding + $vectorSearch against mission_memory.",
    parameters: ["query", "k", "filters"],
    win_rate: 0.86,
    invocations: 538,
  },
];

export function listMockSkills(): Skill[] {
  return SKILLS;
}

export function searchMockSkills(query: string, k = 5): Skill[] {
  const q = query.toLowerCase().trim();
  if (!q) return SKILLS.slice(0, k);
  const tokens = q.split(/\s+/).filter(Boolean);
  return SKILLS.map((s) => {
    const blob = `${s.name} ${s.summary} ${s.agent}`.toLowerCase();
    const overlap = tokens.filter((t) => blob.includes(t)).length;
    const score = overlap === 0 ? 0.3 : Math.min(0.99, 0.55 + overlap * 0.1);
    return { ...s, score };
  })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, k);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Self-evolution proof (plan §9 / SM-1) — three takes of the demo scenario
// ─────────────────────────────────────────────────────────────────────────────

const EXPERIMENTS: ExperimentPoint[] = [
  { scenario: "Whitechapel Trauma", take_n: 1, actual_time_s: 612, reroutes: 2, battery_used: 31 },
  {
    scenario: "Whitechapel Trauma",
    take_n: 2,
    actual_time_s: 568,
    reroutes: 1,
    battery_used: 28,
    lesson: "Avoid Olympic Park NOTAM window between 14:00–16:00 — adds 4 min.",
  },
  {
    scenario: "Whitechapel Trauma",
    take_n: 3,
    actual_time_s: 542,
    reroutes: 1,
    battery_used: 26,
    lesson: "Northern corridor via Hackney Marshes shaves 1.8 km in storm class III.",
  },
  { scenario: "Colindale Cold-Chain", take_n: 1, actual_time_s: 938, reroutes: 1, battery_used: 47 },
  { scenario: "Colindale Cold-Chain", take_n: 2, actual_time_s: 884, reroutes: 1, battery_used: 44 },
  {
    scenario: "Colindale Cold-Chain",
    take_n: 3,
    actual_time_s: 826,
    reroutes: 0,
    battery_used: 42,
    lesson: "Pre-cool payload bay 90 s before lift to halve cold-chain breach risk.",
  },
];

export function getMockExperiments(): ExperimentPoint[] {
  return EXPERIMENTS;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Mission lifecycle simulator
// ─────────────────────────────────────────────────────────────────────────────

const TELEMETRY_HZ = 2; // 2 ticks/sec
const SIM_SPEED_MULTIPLIER = 12; // 1 sim-second = ~12 wall-seconds compressed

interface SimRunner {
  cancel: () => void;
}

function logEvent(
  mission: Mission,
  drone: Drone,
  event: FlightLog["event"],
  message: string,
  meta?: Record<string, unknown>,
): void {
  const log: FlightLog = {
    id: nextId("log"),
    ts: Date.now(),
    mission_id: mission.id,
    drone_id: drone.id,
    event,
    message,
    ...(meta !== undefined ? { meta } : {}),
  };
  FLIGHT_LOGS.unshift(log);
  if (FLIGHT_LOGS.length > 500) FLIGHT_LOGS.pop();
  bus.emit({ type: "flight_log", log });
}

function pushAgentMessage(msg: Omit<AgentMessage, "id" | "ts"> & { ts?: number }): void {
  const full: AgentMessage = {
    ...msg,
    id: nextId("agm"),
    ts: msg.ts ?? Date.now(),
  };
  AGENT_MESSAGES.unshift(full);
  if (AGENT_MESSAGES.length > 500) AGENT_MESSAGES.pop();
  bus.emit({ type: "agent_message", message: full });
}

function setMission(mission: Mission): void {
  MISSIONS.set(mission.id, mission);
  bus.emit({ type: "mission_update", mission: { ...mission } });
}

function setDrone(drone: Drone): void {
  DRONES = DRONES.map((d) => (d.id === drone.id ? drone : d));
  bus.emit({ type: "drone_update", drone: { ...drone } });
}

function buildRoute(originId: string, deliveries: Delivery[]): Waypoint[] {
  const origin = FACILITIES.find((f) => f.id === originId) ?? FACILITIES[FACILITIES.length - 1]!;
  const waypoints: Waypoint[] = [{ position: origin.position, label: origin.name }];
  for (const d of deliveries) {
    const dest = FACILITIES.find((f) => f.id === d.destination_id);
    if (!dest) continue;
    waypoints.push({ position: dest.position, label: dest.name });
  }
  // Return-to-base
  waypoints.push({ position: origin.position, label: `${origin.name} (return)` });
  return waypoints;
}

function pickDrone(): Drone | null {
  // Only ever assign drones that are not already committed to another mission.
  // Falling back to anything-not-fault would happily hand back an in_transit
  // drone — two parallel simulators then race on setDrone and the marker
  // teleports between two routes on the map.
  return (
    DRONES.find((d) => d.status === "idle" && d.battery > 50) ??
    DRONES.find((d) => d.status === "idle" || d.status === "charging") ??
    null
  );
}

function estimateMissionSeconds(route: Waypoint[]): number {
  let metres = 0;
  for (let i = 1; i < route.length; i++) {
    metres += haversineMeters(route[i - 1]!.position, route[i]!.position);
  }
  // Drone cruise speed ≈ 15 m/s + 25 s handover per delivery.
  return Math.round(metres / 15 + (route.length - 2) * 25);
}

function simulateMission(missionId: string): SimRunner {
  const mission = MISSIONS.get(missionId);
  if (!mission) return { cancel: () => undefined };
  const drone = DRONES.find((d) => d.id === mission.drone_id);
  if (!drone) return { cancel: () => undefined };

  let cancelled = false;
  const tickMs = 1000 / TELEMETRY_HZ;

  const run = async () => {
    setDrone({ ...drone, status: "preflight", current_mission_id: mission.id });
    setMission({ ...mission, status: "assigned" });

    // Planner cascade — short, opinionated agent chatter that the UI streams.
    const cascade: Array<[AgentMessageKind, string, string]> = [
      ["supervisor", "Supervisor", `Routing dispatch for ${mission.delivery_ids.length} cargo(s).`],
      ["interpreter", "Interpreter", `Parsed intent → priority=high, region=Greater London.`],
      ["memory_query", "Memory", `$vectorSearch(mission_memory, k=5) → 5 hits, top score 0.91.`],
      ["geofence", "Geofence", `Active NFZs intersect: 0; corridor green.`],
      ["weather", "Weather", `Last 60 min: stable; gust 8 kt @ 240°.`],
      ["preflight", "Preflight", `${drone.id} battery=${drone.battery}%, payload bay nominal.`],
      ["planner", "Planner", `OR-Tools solved in 84 ms · 3 stops · ETA ${formatEta(mission.eta_seconds)}.`],
      ["dispatch", "Dispatch", `Assigning ${drone.id} → mission ${mission.id.slice(-6)}.`],
    ];
    for (const [kind, agent, text] of cascade) {
      if (cancelled) return;
      pushAgentMessage({ kind, agent, text, mission_id: mission.id });
      await sleep(180);
    }

    logEvent(mission, drone, "preflight_ok", "Preflight checklist green.");
    await sleep(220);
    logEvent(mission, drone, "takeoff", `${drone.id} airborne from ${mission.origin_id}.`);

    setMission({ ...mission, status: "in_transit", started_at: Date.now() });
    setDrone({ ...drone, status: "in_transit" });

    // Walk every leg.
    for (let leg = 1; leg < mission.route.length; leg++) {
      if (cancelled) return;
      const a = mission.route[leg - 1]!.position;
      const b = mission.route[leg]!.position;
      const dist = haversineMeters(a, b);
      const legSeconds = Math.max(8, Math.round(dist / 15));
      const ticks = Math.max(2, Math.round((legSeconds * TELEMETRY_HZ) / SIM_SPEED_MULTIPLIER));
      const heading = bearingDeg(a, b);

      for (let i = 1; i <= ticks; i++) {
        if (cancelled) return;
        const t = i / ticks;
        const pos: LngLat = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
        const battery = Math.max(20, drone.battery - leg * 4 - t * 2);
        const payloadTemp = mission.delivery_ids.length > 0
          ? Math.max(2, 4 + Math.sin((Date.now() / 1000) % 6) * 0.6)
          : null;

        const frame: TelemetryFrame = {
          ts: Date.now(),
          mission_id: mission.id,
          drone_id: drone.id,
          position: pos,
          altitude_m: 60 + Math.sin(Date.now() / 800) * 4,
          speed_mps: 14 + Math.cos(Date.now() / 1000) * 2,
          heading_deg: heading,
          battery,
          payload_temp_c: payloadTemp,
          progress: (leg - 1 + t) / (mission.route.length - 1),
        };
        bus.emit({ type: "telemetry", frame });

        // Refresh drone snapshot occasionally — read the live drone from the
        // DRONES array so transitions written by other code (status, current
        // mission id) survive across the spread.
        if (i === ticks || i % 4 === 0) {
          const liveDrone = DRONES.find((d) => d.id === drone.id) ?? drone;
          setDrone({
            ...liveDrone,
            status: "in_transit",
            current_mission_id: mission.id,
            position: pos,
            heading_deg: heading,
            battery,
            payload_temp_c: payloadTemp,
            last_seen: Date.now(),
          });
        }

        await sleep(tickMs);
      }

      // Maybe inject a reroute on the second leg of the first scenario.  Read
      // the live mission from the store rather than the captured snapshot —
      // the store has the latest status/started_at from the takeoff transition
      // above, and overwriting it with the stale snapshot would briefly flip
      // the badge back to "queued".
      const live = MISSIONS.get(mission.id);
      if (live && leg === 1 && live.delivery_ids.length >= 2 && !live.reroutes.length) {
        const updated: Mission = {
          ...live,
          reroutes: [...live.reroutes, { ts: Date.now(), reason: "Storm class III near Homerton" }],
        };
        MISSIONS.set(updated.id, updated);
        logEvent(updated, drone, "reroute", "ReplannerAgent: shifted to northern corridor (+0.3 km, −80 s).", {
          reason: "weather",
        });
        pushAgentMessage({
          kind: "replanner",
          agent: "Replanner",
          text: "Storm class III over Homerton — switching to northern corridor via Hackney Marshes.",
          mission_id: updated.id,
        });
        bus.emit({ type: "mission_update", mission: { ...updated } });
      }

      if (leg < mission.route.length - 1) {
        logEvent(mission, drone, "waypoint_reached", `Reached ${mission.route[leg]!.label}.`);
        const dId = mission.delivery_ids[leg - 1];
        if (dId) {
          const delivery = DELIVERIES.get(dId);
          if (delivery) {
            const updatedDelivery: Delivery = { ...delivery, status: "delivered" };
            DELIVERIES.set(dId, updatedDelivery);
            logEvent(mission, drone, "delivery_handover", `Handover: ${updatedDelivery.id.slice(-6)} → ${mission.route[leg]!.label}.`);
            pushAgentMessage({
              kind: "narrator",
              agent: "Narrator",
              text: `Cargo ${updatedDelivery.id.slice(-6)} signed for at ${mission.route[leg]!.label}.`,
              mission_id: mission.id,
            });
          }
        }
      } else {
        logEvent(mission, drone, "landing", `Landed at ${mission.route[leg]!.label}.`);
      }
    }

    if (cancelled) return;

    const live = MISSIONS.get(mission.id) ?? mission;
    const completed: Mission = {
      ...live,
      status: "completed",
      completed_at: Date.now(),
      // Read started_at from the live mission — the captured `mission` snapshot
      // is the original "queued" record from line 559 and never had started_at
      // assigned, which would inflate actual_seconds by the preflight cascade.
      actual_seconds: Math.round((Date.now() - (live.started_at ?? live.created_at)) / 1000),
    };
    setMission(completed);
    // Preserve the live drone state (depleted battery, final position) when
    // transitioning back to idle.  Spreading the captured snapshot would
    // restore the pre-flight battery and origin position.
    const finalDrone = DRONES.find((d) => d.id === drone.id) ?? drone;
    setDrone({
      ...finalDrone,
      status: "idle",
      current_mission_id: null,
      payload_temp_c: null,
      last_seen: Date.now(),
    });
    logEvent(completed, finalDrone, "mission_complete", "Mission complete · all cargo signed for.");

    pushAgentMessage({
      kind: "reflection",
      agent: "ReflectionAgent",
      text: "Lesson recorded: northern corridor saves ~80 s in storm class III. Embedded to mission_memory.",
      mission_id: mission.id,
    });
    MEMORY.unshift({
      id: nextId("mem"),
      kind: "reflection",
      text: `Mission ${completed.id.slice(-6)} · ${completed.actual_seconds ?? 0} s actual · 1 reroute · ${completed.reroutes[0]?.reason ?? "no weather event"}.`,
      score: 0.86,
      metadata: {
        mission_id: completed.id,
        success: true,
        take_n: completed.take_n,
      },
      created_at: Date.now(),
    });
  };

  void run();

  return { cancel: () => { cancelled = true; } };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function formatEta(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m} min ${s} s`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Public API exposed to lib/api.ts
// ─────────────────────────────────────────────────────────────────────────────

export function listMockMissions(): Mission[] {
  return Array.from(MISSIONS.values()).sort((a, b) => b.created_at - a.created_at);
}

export function getMockMission(id: string): {
  mission: Mission | null;
  deliveries: Delivery[];
  flight_logs: FlightLog[];
} {
  const mission = MISSIONS.get(id) ?? null;
  if (!mission) return { mission: null, deliveries: [], flight_logs: [] };
  const deliveries = mission.delivery_ids
    .map((d) => DELIVERIES.get(d))
    .filter((d): d is Delivery => Boolean(d));
  const flight_logs = FLIGHT_LOGS.filter((l) => l.mission_id === id).slice(0, 50);
  return { mission, deliveries, flight_logs };
}

export interface CreateMissionPayload {
  deliveries: Array<{
    destination_id: string;
    supply: Supply;
    payload_weight_kg: number;
    priority?: "low" | "normal" | "high" | "critical";
    cold_chain_required?: boolean;
  }>;
  origin_id?: string;
  notes?: string;
  scenario?: string;
}

export interface CreateMissionOptions {
  /**
   * Skip the planner-cascade simulation.  Used by ensureMockSeed to pre-stage a
   * historical "completed" mission without racing the simulator's status
   * transitions back to in_transit.
   */
  skipSim?: boolean;
}

export function createMockMission(
  payload: CreateMissionPayload,
  options: CreateMissionOptions = {},
): {
  mission_id: string;
  delivery_ids: string[];
  drone_id: string;
  eta_seconds: number;
} {
  const drone = pickDrone();
  if (!drone) throw new Error("no drone available");
  const originId = payload.origin_id ?? "fac_depot_canary";
  const deliveries = payload.deliveries.map<Delivery>((d) => {
    const dest = FACILITIES.find((f) => f.id === d.destination_id);
    return {
      id: nextId("del"),
      destination_id: d.destination_id,
      ...(dest?.name !== undefined ? { destination_name: dest.name } : {}),
      supply: d.supply,
      payload_weight_kg: d.payload_weight_kg,
      priority: d.priority ?? "normal",
      cold_chain_required: d.cold_chain_required ?? false,
      status: "in_transit",
    };
  });
  for (const d of deliveries) DELIVERIES.set(d.id, d);
  const route = buildRoute(originId, deliveries);
  const eta = estimateMissionSeconds(route);
  const id = nextId("msn");
  const mission: Mission = {
    id,
    status: "queued",
    drone_id: drone.id,
    created_at: Date.now(),
    eta_seconds: eta,
    origin_id: originId,
    delivery_ids: deliveries.map((d) => d.id),
    route,
    reroutes: [],
    risk_score: 28,
    risk_recommendation: "go",
    ...(payload.scenario !== undefined ? { scenario: payload.scenario } : {}),
  };
  MISSIONS.set(id, mission);
  logEvent(mission, drone, "mission_created", `Mission queued with ${deliveries.length} cargo(s).`);
  bus.emit({ type: "mission_update", mission: { ...mission } });
  // Kick off the simulation on next tick so subscribers can attach.
  if (!options.skipSim) {
    setTimeout(() => simulateMission(id), 50);
  }
  return {
    mission_id: id,
    delivery_ids: deliveries.map((d) => d.id),
    drone_id: drone.id,
    eta_seconds: eta,
  };
}

// Pre-seed the mock with one historical, completed mission so the dashboard is
// not empty on first paint and Playwright can assert on real DOM.
export function ensureMockSeed(): void {
  if (MISSIONS.size > 0) return;
  const past = createMockMission(
    {
      deliveries: [
        { destination_id: "fac_royal_london", supply: "o_neg_blood", payload_weight_kg: 0.6, priority: "critical", cold_chain_required: true },
        { destination_id: "fac_kings", supply: "defib", payload_weight_kg: 1.8, priority: "high" },
      ],
      scenario: "Whitechapel Trauma",
    },
    { skipSim: true },
  );
  // Stage the historical mission as fully completed up-front; with skipSim no
  // background simulation will overwrite this transition.
  const m = MISSIONS.get(past.mission_id);
  if (m) {
    const startedAt = m.created_at - 542_000;
    setMission({
      ...m,
      status: "completed",
      started_at: startedAt,
      completed_at: Date.now(),
      actual_seconds: 542,
    });
    // Idle the drone the seed assignment grabbed so the next dispatch can
    // pick it cleanly.
    const seedDrone = DRONES.find((d) => d.id === m.drone_id);
    if (seedDrone) {
      setDrone({ ...seedDrone, status: "idle", current_mission_id: null });
    }
  }
}

export function getMockAgentMessages(filters: {
  kind?: string;
  mission_id?: string;
  operator_id?: string;
}): AgentMessage[] {
  return AGENT_MESSAGES.filter((m) => {
    if (filters.kind && m.kind !== filters.kind) return false;
    if (filters.mission_id && m.mission_id !== filters.mission_id) return false;
    if (filters.operator_id && m.operator_id !== filters.operator_id) return false;
    return true;
  });
}

export function injectMockToast(level: "info" | "success" | "error", text: string): void {
  pushAgentMessage({ kind: "narrator", agent: "Mission Control", text, meta: { level } });
}
