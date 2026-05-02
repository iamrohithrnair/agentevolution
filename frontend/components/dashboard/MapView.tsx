"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";

interface MapViewProps {
  missionId?: string;
  height?: number;
  followDrone?: string;
  showFacilities?: boolean;
  showNoFly?: boolean;
}

/**
 * Leaflet pulls in `window` at module scope, so we hard-code SSR off and show a
 * sized skeleton while the heavy chunk loads.  This avoids any flash of
 * unstyled content during the route transition.
 */
const ClientMap = dynamic(() => import("./MapView.client"), {
  ssr: false,
  loading: () => (
    <Skeleton
      className="rounded-lg"
      style={{ height: "var(--map-height, 480px)" }}
      aria-label="Loading map"
    />
  ),
});

export function MapView(props: MapViewProps) {
  const height = props.height ?? 480;
  return (
    <div style={{ ["--map-height" as string]: `${height}px` } as React.CSSProperties}>
      <ClientMap {...props} />
    </div>
  );
}
