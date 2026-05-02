"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Polygon,
  Polyline,
  CircleMarker,
  Marker,
  Tooltip as LeafletTooltip,
  Popup,
  useMap,
} from "react-leaflet";
import L, { type LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";

import { listFacilities, listNoFlyZones, listDrones, listMissions } from "@/lib/api";
import { openDashboardSocket, openMissionSocket } from "@/lib/ws";
import type { Drone, Facility, Mission, NoFlyZone, TelemetryFrame } from "@/lib/types";
import { formatBattery, formatTemp } from "@/lib/format";
import { Badge } from "@/components/ui/badge";

interface Props {
  missionId?: string;
  height?: number;
  followDrone?: string;
  showFacilities?: boolean;
  showNoFly?: boolean;
}

const DEFAULT_CENTER: [number, number] = [51.515, -0.072]; // central London
const DEFAULT_ZOOM = 12;

const facilityIcon = (label: string) =>
  L.divIcon({
    className: "dronan-facility-icon",
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `
      <span style="
        display:grid;place-items:center;width:28px;height:28px;
        border-radius:9999px;background:var(--color-accent-soft);
        color:var(--color-accent-fg);font-size:14px;
        box-shadow:var(--shadow-1);border:1px solid var(--color-border);
      " title="${label}">⚕</span>
    `,
  });

const droneIcon = (heading: number, status: Drone["status"]) => {
  const airborne = status === "in_transit" || status === "flying" || status === "executing";
  const bg = airborne ? "var(--color-success)" : "var(--color-accent)";
  return L.divIcon({
    className: "dronan-drone-icon",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    html: `
      <span style="
        display:grid;place-items:center;width:36px;height:36px;
        border-radius:9999px;
        background:${bg};
        color:#fff;font-size:14px;box-shadow:var(--shadow-2);
        transform:rotate(${heading}deg);transition:transform 600ms var(--ease-out-soft);
      ">✈</span>
    `,
  });
};

function Recenter({ to }: { to: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (!to) return;
    map.panTo(to, { animate: true, duration: 0.4 });
  }, [to, map]);
  return null;
}

function FitBoundsOnce({ points }: { points: Array<[number, number]> }) {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || points.length < 2) return;
    const b: LatLngBoundsExpression = points.map(([lon, lat]) => [lat, lon] as [number, number]);
    map.fitBounds(b, { padding: [40, 40] });
    fitted.current = true;
  }, [points, map]);
  return null;
}

export default function MapView({
  missionId,
  height = 480,
  followDrone,
  showFacilities = true,
  showNoFly = true,
}: Props) {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [zones, setZones] = useState<NoFlyZone[]>([]);
  const [drones, setDrones] = useState<Record<string, Drone>>({});
  const [missions, setMissions] = useState<Record<string, Mission>>({});
  const [trails, setTrails] = useState<Record<string, Array<[number, number]>>>({});
  const [follow, setFollow] = useState<[number, number] | null>(null);

  const MOVING_STATUSES = new Set(["in_transit", "flying", "executing"]);

  // Initial fetch
  useEffect(() => {
    let cancelled = false;
    Promise.all([listFacilities(), listNoFlyZones(), listDrones(), listMissions()]).then(
      ([f, n, d, m]) => {
        if (cancelled) return;
        setFacilities(f);
        setZones(n);
        setDrones(Object.fromEntries(d.map((x) => [x.id, x])));
        setMissions(Object.fromEntries(m.map((x) => [x.id, x])));
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  // Live drone + mission updates
  useEffect(() => {
    const appendTrail = (id: string, pos: [number, number]) =>
      setTrails((t) => {
        const prev = t[id] ?? [];
        const last = prev[prev.length - 1];
        // Skip duplicate identical points to keep the trail clean.
        if (last && last[0] === pos[0] && last[1] === pos[1]) return t;
        const next = [...prev, pos].slice(-120);
        return { ...t, [id]: next };
      });

    const handleDrone = (d: Drone) => {
      setDrones((s) => ({ ...s, [d.id]: d }));
      if (d.position && MOVING_STATUSES.has(d.status)) {
        appendTrail(d.id, d.position);
      } else if (d.status === "idle") {
        setTrails((t) => {
          if (!t[d.id]) return t;
          const copy = { ...t };
          delete copy[d.id];
          return copy;
        });
      }
    };

    const handleMission = (m: Mission) =>
      setMissions((s) => ({ ...s, [m.id]: { ...s[m.id], ...m } }));

    if (missionId) {
      const sock = openMissionSocket(missionId);
      const offT = sock.on("telemetry", (frame: TelemetryFrame) => {
        setDrones((s) => {
          const prev = s[frame.drone_id];
          if (!prev) return s;
          return {
            ...s,
            [frame.drone_id]: {
              ...prev,
              position: frame.position,
              heading_deg: frame.heading_deg,
              battery: frame.battery,
              status: "in_transit",
              last_seen: frame.ts,
              payload_temp_c: frame.payload_temp_c,
            },
          };
        });
        appendTrail(frame.drone_id, frame.position);
        if (followDrone === frame.drone_id) {
          setFollow([frame.position[1], frame.position[0]]);
        }
      });
      const offD = sock.on("drone_update", handleDrone);
      const offM = sock.on("mission_update", handleMission);
      return () => {
        offT();
        offD();
        offM();
        sock.close();
      };
    }

    const sock = openDashboardSocket();
    const offD = sock.on("drone_update", handleDrone);
    const offM = sock.on("mission_update", handleMission);
    return () => {
      offD();
      offM();
      sock.close();
    };
  }, [missionId, followDrone]);

  const droneList = useMemo(() => Object.values(drones), [drones]);

  const fitPoints = useMemo<Array<[number, number]>>(
    () => [
      ...facilities.slice(0, 6).map((f) => f.position),
      ...droneList.map((d) => d.position),
    ],
    [facilities, droneList],
  );

  return (
    <div
      className="relative overflow-hidden rounded-lg border border-[var(--color-border)] shadow-[var(--shadow-1)]"
      style={{ height }}
      data-testid="map-view"
    >
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        scrollWheelZoom
        zoomControl={false}
        className="h-full w-full"
        attributionControl={false}
      >
        <TileLayer
          attribution="© OSM · Carto"
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
          subdomains={["a", "b", "c", "d"]}
        />
        <FitBoundsOnce points={fitPoints} />
        <Recenter to={follow} />

        {showNoFly &&
          zones.map((z) => (
            <Polygon
              key={z.id}
              positions={z.geometry.coordinates[0]!.map(([lon, lat]) => [lat, lon] as [number, number])}
              pathOptions={{
                color: "var(--color-danger)",
                fillColor: "var(--color-danger)",
                fillOpacity: 0.16,
                weight: 1,
                opacity: 0.85,
              }}
            >
              <LeafletTooltip>
                <strong>{z.name}</strong> · {z.severity}
              </LeafletTooltip>
            </Polygon>
          ))}

        {showFacilities &&
          facilities.map((f) => (
            <Marker key={f.id} position={[f.position[1], f.position[0]]} icon={facilityIcon(f.name)}>
              <Popup>
                <div className="space-y-1 text-xs">
                  <p className="font-semibold">{f.name}</p>
                  <p className="text-[var(--color-fg-muted)]">{f.address}</p>
                  <p className="capitalize text-[var(--color-fg-muted)]">{f.type.replace("_", " ")}</p>
                </div>
              </Popup>
            </Marker>
          ))}

        {/* Active missions — planned path (dashed) + route waypoints */}
        {Object.values(missions)
          .filter(
            (m) => m.status !== "completed" && m.status !== "aborted" && (m.route?.length ?? 0) >= 2,
          )
          .map((m) => {
            const coords = m.route
              .map((w) => w.position)
              .filter((p) => Array.isArray(p) && p.length === 2 && (p[0] !== 0 || p[1] !== 0))
              .map(([lon, lat]) => [lat, lon] as [number, number]);
            if (coords.length < 2) return null;
            return (
              <span key={`mr-${m.id}`}>
                <Polyline
                  positions={coords}
                  pathOptions={{
                    color: "var(--color-accent)",
                    weight: 3,
                    opacity: 0.7,
                    dashArray: "6 8",
                  }}
                >
                  <LeafletTooltip sticky>
                    <strong>{m.id}</strong> · planned · {m.route.length} waypoints
                    {m.reroutes && m.reroutes.length > 0
                      ? ` · ${m.reroutes.length} reroute${m.reroutes.length === 1 ? "" : "s"}`
                      : ""}
                  </LeafletTooltip>
                </Polyline>
                {m.route.map((w, i) => (
                  <CircleMarker
                    key={`wp-${m.id}-${i}`}
                    center={[w.position[1], w.position[0]]}
                    radius={4}
                    pathOptions={{
                      color: "var(--color-accent)",
                      fillColor: "var(--color-bg)",
                      fillOpacity: 1,
                      weight: 2,
                    }}
                  >
                    <LeafletTooltip>
                      {w.label || `waypoint ${i + 1}`}
                    </LeafletTooltip>
                  </CircleMarker>
                ))}
              </span>
            );
          })}

        {/* Drone trails — actual path flown so far */}
        {Object.entries(trails).map(([id, points]) => {
          if (points.length < 2) return null;
          return (
            <Polyline
              key={`trail-${id}`}
              positions={points.map(([lon, lat]) => [lat, lon] as [number, number])}
              pathOptions={{
                color: "var(--color-success)",
                weight: 4,
                opacity: 0.85,
              }}
            />
          );
        })}

        {droneList.map((d) => (
          <Marker
            key={d.id}
            position={[d.position[1], d.position[0]]}
            icon={droneIcon(d.heading_deg, d.status)}
          >
            <Popup>
              <div className="space-y-1.5 text-xs">
                <p className="font-semibold">{d.id}</p>
                <p className="capitalize text-[var(--color-fg-muted)]">Status: {d.status.replace("_", " ")}</p>
                <p className="text-[var(--color-fg-muted)]">Battery: {formatBattery(d.battery)}</p>
                <p className="text-[var(--color-fg-muted)]">
                  Heading: {Math.round(d.heading_deg)}°
                </p>
                <p className="text-[var(--color-fg-muted)]">
                  Payload temp: {formatTemp(d.payload_temp_c)}
                </p>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* Status chip overlay */}
      <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2">
        <Badge variant="success" className="pointer-events-auto gap-1.5 backdrop-blur-sm">
          <span
            className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-dronan-pulse"
            aria-hidden
          />
          Live · {droneList.length} drone{droneList.length === 1 ? "" : "s"}
        </Badge>
        {showNoFly && zones.length > 0 && (
          <Badge variant="danger" className="pointer-events-auto backdrop-blur-sm">
            {zones.length} NFZ active
          </Badge>
        )}
      </div>
    </div>
  );
}
