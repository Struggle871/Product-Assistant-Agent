# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from celery import Celery
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.infrastructure.object_store import ObjectStore
from app.rag.service import process_document

celery_app = Celery(
    "product_assistant",
    broker=get_settings().redis_url,
    backend=get_settings().redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)


@celery_app.task(name="product_assistant.healthcheck")
def healthcheck_task() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(
    bind=True,
    name="product_assistant.ingest_document",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def ingest_document_task(self: object, document_id: str, job_id: str) -> dict[str, str]:
    import asyncio

    async def run() -> None:
        engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await process_document(session, ObjectStore(), document_id, job_id)
        await engine.dispose()

    asyncio.run(run())
    return {"document_id": document_id, "job_id": job_id, "status": "succeeded"}


def enqueue_ingestion(document_id: str, job_id: str) -> None:
    celery_app.send_task(
        "product_assistant.ingest_document",
        args=[document_id, job_id],
    )
