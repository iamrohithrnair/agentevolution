"""Pydantic v2 schemas for every collection in `02-mongodb-data-model.md`.

These models are validated at the API boundary; the matching ``$jsonSchema``
validators (defence in depth) live in :mod:`backend.dronan.bootstrap`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[
    str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)
]


def utcnow() -> datetime:
    """UTC-aware ``datetime.now()``."""
    return datetime.now(timezone.utc)


class MongoModel(BaseModel):
    """Base for every persisted document."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        extra="forbid",
    )
    id: Optional[PyObjectId] = Field(default=None, alias="_id")


# ---------------------------------------------------------------------------
# Geometry helpers (GeoJSON dicts)
# ---------------------------------------------------------------------------
GeoPoint = dict  # {"type":"Point","coordinates":[lon,lat]}
GeoPolygon = dict  # {"type":"Polygon","coordinates":[[[lon,lat], ...]]}


def point(lon: float, lat: float) -> GeoPoint:
    return {"type": "Point", "coordinates": [float(lon), float(lat)]}


def polygon(rings: list[list[tuple[float, float]]]) -> GeoPolygon:
    return {
        "type": "Polygon",
        "coordinates": [[[float(lon), float(lat)] for lon, lat in ring] for ring in rings],
    }


# ---------------------------------------------------------------------------
# 1 · facilities
# ---------------------------------------------------------------------------
class AirsimXY(BaseModel):
    x: float
    y: float
    z: float = -30.0


class Facility(MongoModel):
    name: str
    type: Literal["hospital", "clinic", "depot", "warehouse", "field_camp"]
    region: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    beds: Optional[int] = None
    capabilities: list[str] = Field(default_factory=list)
    location: GeoPoint
    airsim_xy: AirsimXY
    description: Optional[str] = None
    source: Literal["xlsx", "config", "manual", "import"] = "xlsx"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# 2 · no_fly_zones
# ---------------------------------------------------------------------------
NfzSource = Literal["FAA", "PDOK", "UK_CAA", "EASA", "TFR", "INTERNAL"]
NfzSeverity = Literal["advisory", "restricted", "prohibited"]


class NoFlyZone(MongoModel):
    name: str
    source: NfzSource
    country: str
    severity: NfzSeverity
    altitude_floor_m: float = 0.0
    altitude_ceiling_m: float = 120.0
    geometry: GeoPolygon
    effective_from: datetime
    effective_to: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# 3 · weather_observations (time-series)
# ---------------------------------------------------------------------------
class WeatherObservation(BaseModel):
    ts: datetime
    location_id: str
    wind_speed_ms: float
    gust_ms: Optional[float] = None
    precipitation_mm_h: float = 0.0
    visibility_m: Optional[float] = None
    temperature_c: Optional[float] = None
    pressure_hpa: Optional[float] = None
    condition: Optional[str] = None
    alerts: list[str] = Field(default_factory=list)
    flyable: bool = True
    source: Literal["openweather", "metoffice", "noaa", "synthetic"] = "openweather"


# ---------------------------------------------------------------------------
# 4 · drones
# ---------------------------------------------------------------------------
DroneStatus = Literal[
    "idle", "flying", "paused", "returning", "low_battery", "charging", "fault", "offline"
]


class Drone(BaseModel):
    """``_id`` is the human-readable name; uses BaseModel rather than MongoModel."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str = Field(alias="_id")  # "Drone1"
    model: str = "Generic-X1"
    status: DroneStatus = "idle"
    battery: float = Field(ge=0, le=100)
    max_payload_kg: float = 5.0
    cruise_speed_ms: float = 15.0
    current_location: Optional[str] = "Depot"
    position: GeoPoint
    alt_m: float = 0.0
    heading_deg: float = 0.0
    current_mission_id: Optional[str] = None
    firmware: str = "1.0.0"
    last_seen: datetime = Field(default_factory=utcnow)
    capabilities: list[str] = Field(default_factory=lambda: ["cold_chain", "camera"])


# ---------------------------------------------------------------------------
# 5 · deliveries
# ---------------------------------------------------------------------------
Priority = Literal["critical", "high", "normal", "low"]
DeliveryStatus = Literal["pending", "assigned", "in_transit", "delivered", "failed", "cancelled"]


class Delivery(MongoModel):
    destination_id: str
    supply: str
    payload_weight_kg: float
    priority: Priority = "normal"
    time_window_minutes: Optional[int] = None
    status: DeliveryStatus = "pending"
    assigned_drone: Optional[str] = None
    mission_id: Optional[str] = None
    requested_by: str
    requested_at: datetime = Field(default_factory=utcnow)
    delivered_at: Optional[datetime] = None
    cold_chain_required: bool = False
    signature_id: Optional[str] = None


# ---------------------------------------------------------------------------
# 6 · missions
# ---------------------------------------------------------------------------
class RouteWaypoint(BaseModel):
    name: str
    lat: float
    lon: float
    alt_m: float = 30.0
    eta: Optional[datetime] = None
    arrived_at: Optional[datetime] = None


class Reroute(BaseModel):
    at: datetime
    reason: str
    from_wp: int
    to_wp: int
    new_segment: list[RouteWaypoint]
    triggered_by_agent: str


class Obstacle(BaseModel):
    at: datetime
    kind: str
    confidence: float
    bbox: Optional[list[float]] = None
    frame_gridfs_id: Optional[str] = None


class WeatherEvent(BaseModel):
    at: datetime
    location_id: str
    wind_speed_ms: float
    note: str


MissionStatus = Literal["planned", "executing", "completed", "failed", "aborted"]


class Mission(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str = Field(alias="_id")
    delivery_ids: list[str] = Field(default_factory=list)
    drone_id: str
    status: MissionStatus = "planned"
    planned_route: list[RouteWaypoint]
    actual_route: list[RouteWaypoint] = Field(default_factory=list)
    reroutes: list[Reroute] = Field(default_factory=list)
    obstacles: list[Obstacle] = Field(default_factory=list)
    weather_events: list[WeatherEvent] = Field(default_factory=list)
    failed_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_distance_m: float = 0.0
    actual_distance_m: float = 0.0
    estimated_battery_pct: float = 0.0
    actual_battery_pct: float = 0.0
    cost_estimate_gbp: float = 0.0


# ---------------------------------------------------------------------------
# 7 · telemetry  (time-series, slim)
# ---------------------------------------------------------------------------
class Telemetry(BaseModel):
    ts: datetime
    drone_id: str
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    battery: float
    payload_kg: float
    motors_pct: list[float] = Field(default_factory=list)
    temperature_c: Optional[float] = None
    cargo_temperature_c: Optional[float] = None
    gps_fix: int = 3
    rssi_dbm: Optional[float] = None
    anomaly_score: Optional[float] = None


# ---------------------------------------------------------------------------
# 10 · mission_memory (vector)
# ---------------------------------------------------------------------------
WeatherClass = Literal["clear", "rain", "snow", "fog", "storm", "wind"]


class MemoryMetadata(BaseModel):
    region: Optional[str] = None
    weather_class: Optional[WeatherClass] = None
    success: Optional[bool] = None
    severity: Optional[str] = None
    lessons: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


MemoryKind = Literal[
    "reflection", "incident", "regulation", "facility_intel", "operator_pref", "skill"
]


class MissionMemory(MongoModel):
    kind: MemoryKind
    title: str
    text: str
    embedding: list[float]
    embedding_model: str = "voyage-3-large"
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    source_collection: Optional[str] = None
    source_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    score_ema: float = 0.0


# ---------------------------------------------------------------------------
# 11 · regulations
# ---------------------------------------------------------------------------
class Regulation(MongoModel):
    code: str
    country: str
    title: str
    version: str
    max_altitude_m: float
    bvlos_allowed: bool
    night_allowed: bool
    over_people_allowed: bool
    max_takeoff_mass_kg: float
    notes_md: str
    effective_from: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# 14 · synthetic_emergencies
# ---------------------------------------------------------------------------
EmergencyType = Literal[
    "respiratory", "cardiac", "trauma", "obstetric",
    "neurological", "metabolic", "pediatric", "other",
]


class SyntheticEmergency(MongoModel):
    ts: datetime
    location_id: str
    location_lat: float
    location_lon: float
    emergency_type: EmergencyType
    severity: int = Field(ge=1, le=5)
    temperature_c: float
    weather_condition: str
    is_holiday: bool = False
    is_event: bool = False
    hour_of_day: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)


# ---------------------------------------------------------------------------
# 15 · agent_skills (vector)
# ---------------------------------------------------------------------------
class ToolSpec(BaseModel):
    name: str
    schema_: dict = Field(alias="schema")
    description: str

    model_config = ConfigDict(populate_by_name=True)


class AgentSkill(MongoModel):
    agent: str
    capability_text: str
    embedding: list[float]
    embedding_model: str = "voyage-3-large"
    tools: list[ToolSpec] = Field(default_factory=list)
    cost_estimate_gbp_per_call: float = 0.0
    avg_latency_ms: float = 0.0
    reliability_score: float = Field(default=1.0, ge=0, le=1)
    side_effect_class: Literal["read", "plan", "actuate", "audit"] = "read"
    version: str = "1.0.0"
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# 16 · agent_messages
# ---------------------------------------------------------------------------
AgentMessageRole = Literal["request", "response", "broadcast", "tool_call", "tool_result"]


class AgentMessage(MongoModel):
    mission_id: Optional[str] = None
    trace_id: str
    span_id: Optional[str] = None
    from_agent: str
    to_agent: str
    role: AgentMessageRole
    content: dict[str, Any]
    context_doc_ids: list[str] = Field(default_factory=list)
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    ts: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# 17 · tool_call_log
# ---------------------------------------------------------------------------
ToolCallStatus = Literal["pending", "success", "error"]


class ToolCallLog(MongoModel):
    idempotency_key: str
    agent: str
    tool: str
    args_hash: str
    args: dict[str, Any]
    status: ToolCallStatus = "pending"
    result_hash: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    attempt: int = 1
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


__all__ = [
    "AgentMessage",
    "AgentSkill",
    "AirsimXY",
    "Delivery",
    "Drone",
    "DroneStatus",
    "Facility",
    "GeoPoint",
    "GeoPolygon",
    "MemoryKind",
    "MemoryMetadata",
    "Mission",
    "MissionMemory",
    "MissionStatus",
    "MongoModel",
    "NoFlyZone",
    "Obstacle",
    "Priority",
    "Regulation",
    "Reroute",
    "RouteWaypoint",
    "SyntheticEmergency",
    "Telemetry",
    "ToolCallLog",
    "ToolSpec",
    "WeatherClass",
    "WeatherEvent",
    "WeatherObservation",
    "point",
    "polygon",
    "utcnow",
]
