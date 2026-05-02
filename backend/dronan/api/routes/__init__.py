"""REST routers — one module per resource."""

from .chat import router as chat_router
from .deliveries import router as deliveries_router
from .drones import router as drones_router
from .facilities import router as facilities_router
from .livekit_token import router as livekit_router
from .memory import router as memory_router
from .missions import router as missions_router
from .nofly import router as nofly_router
from .reports import router as reports_router
from .weather import router as weather_router

__all__ = [
    "chat_router",
    "deliveries_router",
    "drones_router",
    "facilities_router",
    "livekit_router",
    "memory_router",
    "missions_router",
    "nofly_router",
    "reports_router",
    "weather_router",
]
