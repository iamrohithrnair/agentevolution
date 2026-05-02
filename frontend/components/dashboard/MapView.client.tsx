"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Polygon, Marker, Tooltip as LeafletTooltip, Popup, useMap } from "react-leaflet";
import L, { type LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";

import { listFacilities, listNoFlyZones, listDrones } from "@/lib/api";
import { openDashboardSocket, openMissionSocket } from "@/lib/ws";
import type { Drone, Facility, NoFlyZone, TelemetryFrame } from "@/lib/types";
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

const droneIcon = (heading: number, status: Drone["status"]) =>
  L.divIcon({
    className: "dronan-drone-icon",
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    html: `
      <span style="
        display:grid;place-items:center;width:36px;height:36px;
        border-radius:9999px;
        background:${status === "in_transit" ? "var(--color-success)" : "var(--color-accent)"};
        color:#fff;font-size:14px;box-shadow:var(--shadow-2);
        transform:rotate(${heading}deg);transition:transform 600ms var(--ease-out-soft);
      ">✈</span>
    `,
  });

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
  const [follow, setFollow] = useState<[number, number] | null>(null);

  // Initial fetch
  useEffect(() => {
    let cancelled = false;
    Promise.all([listFacilities(), listNoFlyZones(), listDrones()]).then(([f, n, d]) => {
      if (cancelled) return;
      setFacilities(f);
      setZones(n);
      setDrones(Object.fromEntries(d.map((x) => [x.id, x])));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Live drone updates
  useEffect(() => {
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
        if (followDrone === frame.drone_id) {
          setFollow([frame.position[1], frame.position[0]]);
        }
      });
      const offD = sock.on("drone_update", (d: Drone) =>
        setDrones((s) => ({ ...s, [d.id]: d })),
      );
      return () => {
        offT();
        offD();
        sock.close();
      };
    }
    const sock = openDashboardSocket();
    const offD = sock.on("drone_update", (d: Drone) => setDrones((s) => ({ ...s, [d.id]: d })));
    return () => {
      offD();
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
