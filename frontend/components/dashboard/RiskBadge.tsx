import { Badge } from "@/components/ui/badge";
import type { Mission } from "@/lib/types";

export function RiskBadge({ mission }: { mission: Mission }) {
  const score = mission.risk_score ?? 0;
  if (mission.risk_recommendation === "abort" || score >= 70)
    return <Badge variant="danger">risk · abort recommended ({score})</Badge>;
  if (mission.risk_recommendation === "go_with_caution" || score >= 40)
    return <Badge variant="warning">risk · caution ({score})</Badge>;
  return <Badge variant="success">risk · go ({score})</Badge>;
}
