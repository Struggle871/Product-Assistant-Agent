# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

import asyncio
from collections.abc import AsyncIterator
from io import BytesIO

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings


class ObjectStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            use_ssl=settings.minio_secure,
        )

    def ensure_bucket_sync(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    async def put(self, object_key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(self.ensure_bucket_sync)  # type: ignore[arg-type]
        await asyncio.to_thread(  # type: ignore[arg-type]
            self.client.upload_fileobj,
            BytesIO(content),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

    async def read(self, object_key: str) -> bytes:
        response = await asyncio.to_thread(  # type: ignore[arg-type]
            self.client.get_object,
            Bucket=self.bucket,
            Key=object_key,
        )
        body = response["Body"]
        return await asyncio.to_thread(body.read)  # type: ignore[arg-type]

    async def delete(self, object_key: str) -> None:
        await asyncio.to_thread(  # type: ignore[arg-type]
            self.client.delete_object, Bucket=self.bucket, Key=object_key
        )


async def get_object_store() -> AsyncIterator[ObjectStore]:
    yield ObjectStore()
