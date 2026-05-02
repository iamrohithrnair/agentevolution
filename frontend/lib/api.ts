/**
 * Typed REST client for the FastAPI surface defined in
 * prompts/07-backend-fastapi.md.
 *
 * When the real backend is not yet reachable, every method falls through to
 * the in-process mock simulator (`lib/mock.ts`) so the frontend can ship and
 * demo standalone.
 */

import env from "./env";
import {
  createMockMission,
  ensureMockSeed,
  getMockExperiments,
  getMockFacilities,
  getMockMission,
  getMockNoFlyZones,
  getMockDrones,
  injectMockToast,
  listMockMissions,
  listMockReflections,
  listMockSkills,
  searchMockMemory,
  searchMockSkills,
  type CreateMissionPayload,
} from "./mock";
import type {
  Drone,
  ExperimentPoint,
  Facility,
  FlightLog,
  MemoryHit,
  Mission,
  NoFlyZone,
  Skill,
} from "./types";

// Always seed the mock on first import — cheap, idempotent.
ensureMockSeed();

const useMocks = env.useMocks;

export class APIError extends Error {
  constructor(public status: number, public body: string) {
    super(`api ${status}: ${body}`);
  }
}

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const url = `${env.apiBase}${path}`;
  const r = await fetch(url, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "include",
  });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new APIError(r.status, body);
  }
  return r;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Missions
// ─────────────────────────────────────────────────────────────────────────────

export async function listMissions(): Promise<Mission[]> {
  if (useMocks) return listMockMissions();
  return (await authedFetch("/api/missions")).json();
}

export async function getMission(id: string): Promise<{
  mission: Mission | null;
  deliveries: unknown[];
  flight_logs: FlightLog[];
}> {
  if (useMocks) return getMockMission(id);
  return (await authedFetch(`/api/missions/${id}`)).json();
}

export async function createMission(
  payload: CreateMissionPayload,
): Promise<{ mission_id: string; delivery_ids: string[]; drone_id: string; eta_seconds: number }> {
  if (useMocks) return createMockMission(payload);
  return (
    await authedFetch("/api/missions", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    })
  ).json();
}

export async function rerouteMission(
  id: string,
  reason: string,
): Promise<{ ok: true }> {
  if (useMocks) {
    injectMockToast("info", `Manual reroute requested: ${reason}`);
    return { ok: true };
  }
  return (
    await authedFetch(`/api/missions/${id}/reroute`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    })
  ).json();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Drones
// ─────────────────────────────────────────────────────────────────────────────

export async function listDrones(): Promise<Drone[]> {
  if (useMocks) return getMockDrones();
  return (await authedFetch("/api/drones")).json();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Facilities + no-fly zones
// ─────────────────────────────────────────────────────────────────────────────

export async function listFacilities(query?: { q?: string }): Promise<Facility[]> {
  if (useMocks) {
    const all = getMockFacilities();
    if (!query?.q) return all;
    const q = query.q.toLowerCase();
    return all.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.address.toLowerCase().includes(q) ||
        f.region.toLowerCase().includes(q),
    );
  }
  const qs = query?.q ? `?q=${encodeURIComponent(query.q)}` : "";
  return (await authedFetch(`/api/facilities${qs}`)).json();
}

export async function listNoFlyZones(): Promise<NoFlyZone[]> {
  if (useMocks) return getMockNoFlyZones();
  return (await authedFetch("/api/no-fly-zones?active=true")).json();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Memory / skills / analytics
// ─────────────────────────────────────────────────────────────────────────────

export async function memorySearch(
  query: string,
  k = 5,
  filters?: Record<string, unknown>,
): Promise<{ hits: MemoryHit[] }> {
  if (useMocks) return { hits: searchMockMemory(query, k) };
  return (
    await authedFetch("/api/memory/search", {
      method: "POST",
      body: JSON.stringify({ query, k, filters }),
    })
  ).json();
}

export async function listReflections(): Promise<MemoryHit[]> {
  if (useMocks) return listMockReflections();
  return (await authedFetch("/api/memory/reflections")).json();
}

export async function listSkills(): Promise<Skill[]> {
  if (useMocks) return listMockSkills();
  return (await authedFetch("/api/skills")).json();
}

export async function peerSearchSkills(query: string, k = 5): Promise<{ hits: Skill[] }> {
  if (useMocks) return { hits: searchMockSkills(query, k) };
  return (
    await authedFetch("/api/skills/peer-search", {
      method: "POST",
      body: JSON.stringify({ query, k }),
    })
  ).json();
}

export async function listExperiments(): Promise<ExperimentPoint[]> {
  if (useMocks) return getMockExperiments();
  return (await authedFetch("/api/analytics/self-evolution")).json();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Demo affordances (plan §10)
// ─────────────────────────────────────────────────────────────────────────────

export async function simulateWeather(severity: "low" | "medium" | "high" | "extreme") {
  if (useMocks) {
    injectMockToast("info", `Storm injected (${severity}) — Atlas Trigger fanning out.`);
    return { ok: true };
  }
  return (
    await authedFetch("/api/simulate-weather", {
      method: "POST",
      body: JSON.stringify({ location_id: "homerton", severity }),
    })
  ).json();
}

export async function injectObstacle(kind: string) {
  if (useMocks) {
    injectMockToast("info", `Obstacle injected (${kind}).`);
    return { ok: true };
  }
  return (
    await authedFetch("/api/internal/inject-obstacle", {
      method: "POST",
      body: JSON.stringify({ kind, lat: 51.519, lon: -0.063 }),
    })
  ).json();
}

// ─────────────────────────────────────────────────────────────────────────────
//  SSE — chat / agents stream
//
//  Returns an async iterator over `event: <kind>\ndata: <json>\n\n` chunks so
//  components can consume tokens with a `for await` loop.  The mock variant
//  produces a planner/dispatch cascade that ends with `done`.
// ─────────────────────────────────────────────────────────────────────────────

export async function* fetchChatSSE(
  message: string,
  opts: { mission_id?: string } = {},
): AsyncIterable<{ event: string; data: unknown }> {
  if (useMocks) {
    yield { event: "start", data: {} };
    const reply =
      "Affirmative — dispatching the cargo. Planner solved in 84 ms. " +
      "Memory recall returned 5 lessons; the top-scored card flagged a storm corridor. " +
      "Geofence check is clean. Drone Alpha is airborne in 8 seconds.";
    for (const word of reply.split(" ")) {
      await new Promise((r) => setTimeout(r, 40));
      yield { event: "token", data: { text: word + " " } };
    }
    yield { event: "tool", data: { name: "memory.recall", input: { query: message } } };
    yield { event: "done", data: {} };
    return;
  }

  const r = await fetch(`${env.apiBase}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, ...opts }),
    cache: "no-store",
  });
  if (!r.body) return;
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const ev = /event:\s*(.+)/.exec(chunk)?.[1] ?? "message";
      const data = /data:\s*(.+)/.exec(chunk)?.[1] ?? "{}";
      try {
        yield { event: ev, data: JSON.parse(data) };
      } catch {
        yield { event: ev, data };
      }
    }
  }
}

// Re-export mock helpers for components that want to drive the simulator
// directly (e.g. the DemoMenu's "Run Encore" action).
export { ensureMockSeed, injectMockToast };
