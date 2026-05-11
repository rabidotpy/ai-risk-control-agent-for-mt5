"""Tortoise ORM lifecycle.

Schema is auto-generated on every init — fine while the table set is
small and stable. When the schema starts changing in production, swap
`generate_schemas=True` for an Aerich migration step here.
"""

from __future__ import annotations

from tortoise import Tortoise

from ..config import settings


TORTOISE_ORM: dict = {
    "connections": {"default": settings.database_url},
    "apps": {
        "models": {
            "models": ["app.models.analysis"],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}


async def init_db(*, generate_schemas: bool = True) -> None:
    """Initialise Tortoise. Call once at process startup (FastAPI lifespan)."""
    await Tortoise.init(config=TORTOISE_ORM)
    if generate_schemas:
        await Tortoise.generate_schemas(safe=True)


async def close_db() -> None:
    await Tortoise.close_connections()
