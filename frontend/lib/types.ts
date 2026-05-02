/**
 * Typed contracts shared by the Dronan operator console.
 *
 * Mirrors the request/response shapes documented in:
 *   - prompts/07-backend-fastapi.md  (REST + WS + SSE)
 *   - prompts/08-frontend-nextjs.md  (UI consumer expectations)
 *
 * Keep this file framework-free so it can be imported from server, client,
 * route handlers, and Playwright tests alike.
 */

export type LngLat = [number, number]; // [lon, lat] (matches GeoJSON ordering)

export type Supply =
  | "o_neg_blood"
  | "o_pos_blood"
  | "insulin"
  | "vaccine"
  | "defib"
  | "epi"
  | "narcan";

export const SUPPLY_LABELS: Record<Supply, string> = {
  o_neg_blood: "O- blood",
  o_pos_blood: "O+ blood",
  insulin: "Insulin",
  vaccine: "Vaccine kit",
  defib: "Defibrillator",
  epi: "Epinephrine",
  narcan: "Naloxone",
};

export type Priority = "low" | "normal" | "high" | "critical";

export type MissionStatus =
  | "draft"
  | "queued"
  | "assigned"
  | "in_transit"
  | "delivered"
  | "returning"
  | "completed"
  | "aborted";

export type DroneStatus =
  | "idle"
  | "preflight"
  | "in_transit"
  | "returning"
  | "charging"
  | "fault";

export type FacilityType =
  | "hospital"
  | "clinic"
  | "depot"
  | "blood_bank"
  | "pharmacy";

// ─────────────────────────────────────────────────────────────────────────────
//  Domain documents
// ─────────────────────────────────────────────────────────────────────────────

export interface Facility {
  id: string;
  name: string;
  type: FacilityType;
  region: string;
  address: string;
  position: LngLat;
  capabilities: string[];
}

export interface NoFlyZone {
  id: string;
  name: string;
  country: string;
  severity: "low" | "medium" | "high";
  // GeoJSON Polygon
  geometry: {
    type: "Polygon";
    coordinates: LngLat[][];
  };
}

export interface Drone {
  id: string;
  status: DroneStatus;
  battery: number; // 0..100
  position: LngLat;
  heading_deg: number;
  current_mission_id: string | null;
  last_seen: number; // unix ms
  payload_temp_c: number | null;
}

export interface Delivery {
  id: string;
  destination_id: string;
  destination_name?: string;
  supply: Supply;
  payload_weight_kg: number;
  priority: Priority;
  cold_chain_required: boolean;
  status: "pending" | "in_transit" | "delivered" | "failed";
}

export interface Waypoint {
  position: LngLat;
  label: string;
  arrived_at?: number; // unix ms when reached
  eta?: number;        // unix ms
}

export interface Mission {
  id: string;
  status: MissionStatus;
  drone_id: string;
  created_at: number;
  started_at?: number;
  completed_at?: number;
  eta_seconds: number;
  actual_seconds?: number;
  origin_id: string;
  delivery_ids: string[];
  route: Waypoint[];
  reroutes: Array<{ ts: number; reason: string }>;
  risk_score?: number;
  risk_recommendation?: "go" | "go_with_caution" | "abort";
  take_n?: number; // self-evolution take number
  scenario?: string;
}

export interface FlightLog {
  id: string;
  ts: number;
  mission_id: string;
  drone_id: string;
  event:
    | "mission_created"
    | "preflight_ok"
    | "takeoff"
    | "waypoint_reached"
    | "reroute"
    | "delivery_handover"
    | "landing"
    | "anomaly"
    | "weather_alert"
    | "obstacle_detected"
    | "mission_complete"
    | "operator_override";
  message: string;
  meta?: Record<string, unknown>;
}

export interface TelemetryFrame {
  ts: number;
  mission_id: string;
  drone_id: string;
  position: LngLat;
  altitude_m: number;
  speed_mps: number;
  heading_deg: number;
  battery: number;
  payload_temp_c: number | null;
  progress: number; // 0..1 along the active leg
}

// ─────────────────────────────────────────────────────────────────────────────
//  Memory + agent semantics
// ─────────────────────────────────────────────────────────────────────────────

export type MemoryKind =
  | "reflection"
  | "incident"
  | "regulation"
  | "facility_intel"
  | "weather_class"
  | "operator_pref";

export interface MemoryHit {
  id: string;
  kind: MemoryKind;
  text: string;
  score: number; // 0..1
  metadata: {
    region?: string;
    weather_class?: string;
    success?: boolean;
    mission_id?: string;
    take_n?: number;
    [k: string]: unknown;
  };
  created_at: number;
}

export type AgentMessageKind =
  | "user"
  | "supervisor"
  | "interpreter"
  | "memory"
  | "memory_query"
  | "planner"
  | "weather"
  | "geofence"
  | "preflight"
  | "payload"
  | "dispatch"
  | "vision"
  | "replanner"
  | "anomaly"
  | "deconfliction"
  | "narrator"
  | "analyst"
  | "reflection"
  | "demand_forecast"
  | "retrieval_critic"
  | "agent_activity"
  | "tool_call"
  | "incident"
  | "regulation"
  | "facility_intel"
  | "operator_pref"
  | "signature";

export interface AgentMessage {
  id: string;
  ts: number;
  kind: AgentMessageKind;
  mission_id?: string;
  operator_id?: string;
  agent?: string;
  text: string;
  meta?: Record<string, unknown>;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Skills registry
// ─────────────────────────────────────────────────────────────────────────────

export interface Skill {
  skill_id: string;
  name: string;
  agent: string;
  summary: string;
  parameters: string[];
  win_rate: number; // 0..1
  invocations: number;
  score?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Self-evolution analytics
// ─────────────────────────────────────────────────────────────────────────────

export interface ExperimentPoint {
  scenario: string;
  take_n: number;
  actual_time_s: number;
  reroutes: number;
  battery_used: number;
  lesson?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
//  WebSocket envelope
// ─────────────────────────────────────────────────────────────────────────────

export type WSKind =
  | "telemetry"
  | "flight_log"
  | "mission_update"
  | "drone_update"
  | "ack";

export interface WSEnvelope<T = unknown> {
  kind: WSKind;
  doc?: T;
  id?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Chat / SSE
// ─────────────────────────────────────────────────────────────────────────────

export type ChatEvent =
  | { event: "start"; data: Record<string, never> }
  | { event: "token"; data: { text: string } }
  | { event: "tool"; data: { name: string; input?: unknown } }
  | { event: "tool_end"; data: { name: string } }
  | { event: "agent"; data: { agent: string; message: string; mission_id?: string } }
  | { event: "mission"; data: { mission_id: string } }
  | { event: "done"; data: Record<string, never> }
  | { event: "error"; data: { message: string } };

// ─────────────────────────────────────────────────────────────────────────────
//  LiveKit
// ─────────────────────────────────────────────────────────────────────────────

export interface LkSession {
  url: string;
  token: string;
  room: string;
  identity: string;
  mode: "ptt" | "always_on";
  language: "en" | "auto";
}
