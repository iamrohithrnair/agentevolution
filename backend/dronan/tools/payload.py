"""Payload tools — cold-chain prediction + manifest assembly.

``cold_chain_predict`` models bag temperature drift as

    T(t) = T_ambient - (T_ambient - T_initial) * exp(-k * t)

where ``k`` shrinks with ice-pack count. We surface the predicted bag
temperature at ``flight_minutes`` and a boolean ``breach`` flag against the
operator's allowed ceiling.
"""

from __future__ import annotations

import math
from typing import Any

from ._decorator import ToolError, mongo_tool

# Empirical decay constant per ice-pack (per minute). Calibrated so that:
#  - 0 packs / ambient 22 °C / start 4 °C → ≈8.4 °C after 9 min (matches the
#    cold-chain incident card from prompts/02 / seed_demo_memory.py).
#  - 2 packs / ambient 24 °C / start 4 °C → ≈5.5 °C after 9 min.
_K_NO_PACK = 0.08
_K_PER_PACK = 0.05


@mongo_tool(side_effect_class="plan", agent="PayloadAgent")
async def cold_chain_predict(
    *,
    db: Any | None = None,
    initial_temp_c: float,
    ambient_temp_c: float,
    ice_pack_count: int,
    flight_minutes: float,
    bag_ceiling_c: float = 6.0,
) -> dict:
    """Predict bag temperature at ``flight_minutes`` and check the ceiling."""
    if flight_minutes < 0:
        raise ToolError("flight_minutes must be non-negative")

    k = max(0.005, _K_NO_PACK - _K_PER_PACK * ice_pack_count)
    delta = ambient_temp_c - initial_temp_c
    predicted = ambient_temp_c - delta * math.exp(-k * flight_minutes)

    # Recommend extra ice when the predicted exit temperature breaches
    # ceiling AND ambient is high.
    extra_recommended = predicted > bag_ceiling_c and ambient_temp_c >= 22.0

    return {
        "predicted_temp_c": round(predicted, 2),
        "breach": predicted > bag_ceiling_c,
        "recommended_extra_ice_pack": extra_recommended,
        "k_decay": round(k, 4),
    }


@mongo_tool(side_effect_class="plan", agent="PayloadAgent")
async def assemble_manifest(
    *,
    db: Any,
    delivery_ids: list[str],
    drone_id: str,
) -> dict:
    """Aggregate delivery payload weights and cold-chain flags for a drone."""
    if not delivery_ids:
        raise ToolError("assemble_manifest needs at least one delivery_id")

    cursor = db.deliveries.find({"_id": {"$in": delivery_ids}})
    deliveries = await cursor.to_list(length=len(delivery_ids))
    if not deliveries:
        raise ToolError("No deliveries matched the requested IDs")

    drone = await db.drones.find_one({"_id": drone_id})
    if drone is None:
        raise ToolError(f"Unknown drone: {drone_id}")

    total_weight = sum(d.get("payload_weight_kg", 0) for d in deliveries)
    cold_chain_required = any(d.get("cold_chain_required") for d in deliveries)
    over_limit = total_weight > drone.get("max_payload_kg", 5)

    return {
        "drone_id": drone_id,
        "delivery_ids": [d["_id"] for d in deliveries],
        "total_weight_kg": round(total_weight, 3),
        "max_weight_kg": drone.get("max_payload_kg"),
        "over_limit": over_limit,
        "cold_chain_required": cold_chain_required,
        "items": [
            {
                "id": d["_id"],
                "supply": d.get("supply"),
                "weight_kg": d.get("payload_weight_kg"),
                "destination": d.get("destination_id"),
            }
            for d in deliveries
        ],
    }
