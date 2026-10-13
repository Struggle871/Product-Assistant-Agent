"""Check configured infrastructure without printing credentials or modifying data."""

import asyncio
import json

from app.db import engine
from app.health import readiness


async def main() -> bool:
    try:
        ok, statuses = await readiness()
        print(
            json.dumps(
                {
                    "status": "ready" if ok else "not_ready",
                    "dependencies": {
                        item.name: {"ok": item.ok, "detail": item.detail} for item in statuses
                    },
                }
            )
        )
        return ok
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
