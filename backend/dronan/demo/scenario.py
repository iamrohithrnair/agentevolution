"""The canonical *Airport Corridor Storm* scenario.

Deterministic, fully scripted dispatch used by the on-stage encore in
``prompts/11-demo-script.md`` §3 and the self-evolution test
``backend/tests/test_self_evolution.py`` (SM-1).

Why deterministic
-----------------

We must prove Take-3 < 90 % × Take-1 (SM-1) without LLM noise. So:

- Locations, supplies, and priorities are hard-coded.
- The storm and obstacle injections fire at fixed wall-clock offsets from
  ``T0`` (mission start). The runner advances the simulated clock; nothing
  here depends on real wind data.
- The ``request_text`` is the literal voice request the operator says
  on stage; it is the only input the supervisor sees, so re-runs are
  bit-identical given the same ``mission_memory``.

The scenario shape is intentionally close to the LangGraph state schema in
``prompts/03-agents-langgraph.md`` so a future PR can swap the simulated
supervisor for the real one with no edits here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #

#: The exact phrase the operator says on stage. Captured here so STT cassettes
#: and text-mode REPL drives both produce identical states.
SCENARIO_REQUEST_TEXT: str = (
    "DroneFleet, dispatch O-negative blood and pediatric vaccines to Clinic D "
    "now. Storm is rolling in over the Thames; pick the safer corridor."
)


@dataclass(frozen=True)
class Location:
    """A facility node referenced by the planner."""

    id: str
    name: str
    lat: float
    lon: float
    kind: str  # "depot" | "clinic" | "hospital"


@dataclass(frozen=True)
class Supply:
    """An item to deliver. ``cold_chain_max_min`` mirrors the field that
    PayloadAgent gates on (prompts/10 §13.1)."""

    sku: str
    name: str
    quantity: int
    priority: int  # 1 = lowest, 5 = highest
    cold_chain_max_min: int  # 0 = ambient ok


@dataclass(frozen=True)
class Injection:
    """An external event the simulator injects at ``t_offset_s``.

    The runner uses these to make Take-1 expensive (forces a reroute) and to
    let lessons accumulated by ReflectionAgent shorten Take-3.
    """

    t_offset_s: float
    kind: str  # "weather_alert" | "obstacle" | "no_fly_violation" | "anomaly"
    payload: dict[str, str | int | float]


@dataclass(frozen=True)
class Scenario:
    """The full scripted dispatch."""

    id: str
    request_text: str
    locations: tuple[Location, ...]
    supplies: tuple[Supply, ...]
    injections: tuple[Injection, ...]

    # Per-take baseline numbers — ``actual_time_s`` for the cold-cluster Take-1
    # if the Planner picks the Thames corridor at 100 m AGL and is forced to
    # reroute by the wind-shear injection. Calibrated from the rehearsal log
    # in ``prompts/10`` §13.1.
    baseline_actual_time_s: float = 240.0

    # Per-lesson improvement when retrieved by the Planner. The narrative in
    # ``prompts/10`` §13.3 is "29 % faster than Take 1" with 3 corroborating
    # lessons; (3 × 24) / 240 ≈ 30 %, so 24 s/lesson is the right ballpark.
    seconds_saved_per_lesson: float = 24.0

    # The minimum number of lesson cards ReflectionAgent must write per
    # completed mission (SM-2). The simulated supervisor enforces this when
    # writing the post-take reflection block.
    min_lessons_per_take: int = 6

    #: Region/weather class facets used by ``hard_block_corridors_for(region)``
    region: str = "thames_estuary"
    weather_class: str = "gusty"

    #: Tag stamped on every mission_memory doc this scenario produces. The
    #: runner uses it to scope retrieval (so two parallel scenarios don't
    #: cross-contaminate each other's lesson pools).
    tag: str = field(default="")

    def __post_init__(self) -> None:
        # Frozen dataclass — bypass setattr to default ``tag`` from ``id``.
        if not self.tag:
            object.__setattr__(self, "tag", f"scenario:{self.id}")


# --------------------------------------------------------------------------- #
# The single canonical scenario instance.
# --------------------------------------------------------------------------- #


CANONICAL_SCENARIO = Scenario(
    id="airport_corridor_storm",
    request_text=SCENARIO_REQUEST_TEXT,
    locations=(
        Location(id="depot_a", name="London Helideck Depot", lat=51.502, lon=-0.064, kind="depot"),
        Location(
            id="hospital_rl", name="Royal London Hospital", lat=51.518, lon=-0.060, kind="hospital"
        ),
        Location(id="clinic_d", name="Clinic D — Hackney", lat=51.546, lon=-0.057, kind="clinic"),
        Location(
            id="hospital_homerton",
            name="Homerton Hospital",
            lat=51.553,
            lon=-0.045,
            kind="hospital",
        ),
    ),
    supplies=(
        Supply(
            sku="BLD-O-NEG-450",
            name="O-negative blood",
            quantity=2,
            priority=5,
            cold_chain_max_min=14,
        ),
        Supply(
            sku="VAX-PED-MMR", name="Pediatric MMR", quantity=20, priority=4, cold_chain_max_min=20
        ),
    ),
    injections=(
        # Wind-shear over the Thames corridor at T+30 s — the trigger that
        # makes Take-1 reroute. ReflectionAgent should cite this as evidence
        # for ``corridor_avoidance`` and ``weather_threshold`` lessons.
        Injection(
            t_offset_s=30.0,
            kind="weather_alert",
            payload={
                "place": "Thames Estuary corridor",
                "wind_kt": 22,
                "altitude_band_m": "80-120",
                "advisory": "wind shear",
            },
        ),
        # Bird strike obstacle at T+90 s — secondary anomaly to keep Take-1
        # interesting without being unrealistic. ReflectionAgent typically
        # ignores this (single-mission noise; <2 corroborating lessons → no
        # hard-block).
        Injection(
            t_offset_s=90.0,
            kind="obstacle",
            payload={"drone": "Drone 1", "alt": 90, "kind": "bird_strike_warning"},
        ),
    ),
)


def get_scenario(scenario_id: str = "airport_corridor_storm") -> Scenario:
    """Look up a scenario by id. Currently only one is supported."""
    if scenario_id != CANONICAL_SCENARIO.id:
        raise KeyError(f"unknown scenario_id={scenario_id!r}")
    return CANONICAL_SCENARIO
