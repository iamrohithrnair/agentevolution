"""PayloadAgent — manifest build + cold-chain pre-flight."""

from __future__ import annotations

from typing import Any

from ..tools.payload import assemble_manifest, cold_chain_predict
from ._base import agent_node


@agent_node("payload")
async def payload_node(state: dict, *, db: Any) -> dict:
    delivery_ids = list(state.get("delivery_ids") or [])
    drone_id = state.get("drone_id") or "Drone1"

    if not delivery_ids:
        return {"payload_status": {"manifest": None, "cold_chain": None}}

    manifest = await assemble_manifest(
        db=db,
        delivery_ids=delivery_ids,
        drone_id=drone_id,
        idempotency_key=f"manifest:{state.get('mission_id', 'anon')}",
    )

    cold = None
    if manifest.get("cold_chain_required"):
        plan = state.get("plan") or {}
        eta_s = (plan.get("eta_s") or 600)
        cold = await cold_chain_predict(
            initial_temp_c=4.0,
            ambient_temp_c=22.0,
            ice_pack_count=manifest.get("ice_pack_count", 1),
            flight_minutes=eta_s / 60.0,
            idempotency_key=f"cc:{state.get('mission_id', 'anon')}",
        )

    return {
        "payload_status": {"manifest": manifest, "cold_chain": cold},
        "tool_calls": [{"tool": "assemble_manifest", "agent": "payload"}],
    }
