import asyncio
from pathlib import Path

from sqlalchemy import select

from app.db import session_factory
from app.domain.models import Product
from app.infrastructure.object_store import ObjectStore
from app.rag.service import create_document, process_document, seed_catalog


async def main() -> None:
    root = Path(__file__).resolve().parents[2]
    async with session_factory() as session:
        await seed_catalog(session)
        products = (await session.execute(select(Product))).scalars().all()
        product_by_name = {product.name: product.id for product in products}
        for path, product_name in (
            (root / "data/demo/archer-ax55.md", "Archer AX55"),
            (root / "data/demo/hp-m110w.md", "LaserJet M110w"),
            (root / "data/demo/tapo-c200.md", "Tapo C200"),
        ):
            content = path.read_bytes()
            document, job, is_new = await create_document(
                session,
                ObjectStore(),
                content=content,
                filename=path.name,
                content_type="text/markdown",
                product_id=product_by_name[product_name],
                product_model_id=None,
                product_version_id=None,
                title=path.stem,
                language="zh-CN",
                document_type="manual",
            )
            if is_new:
                await process_document(session, ObjectStore(), document.id, job.id)
    print("Demo catalog and documents are ready.")


if __name__ == "__main__":
    asyncio.run(main())
