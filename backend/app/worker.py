# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from celery import Celery

from app.config import get_settings

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
