import asyncio

from app.db import session_factory
from app.rag.service import seed_catalog


async def main() -> None:
    async with session_factory() as session:
        created = await seed_catalog(session)
    print(f"Catalog ready; created {created} records.")


if __name__ == "__main__":
    asyncio.run(main())
