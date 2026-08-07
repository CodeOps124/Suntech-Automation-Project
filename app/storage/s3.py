"""S3-compatible object storage client.

Written against the S3 protocol, NOT the AWS SDK by intent (CLAUDE.md §1: no
cloud vendor lock-in). boto3 happens to be the client library, but it points at
whatever S3_ENDPOINT_URL is — MinIO in dev, any S3-compatible bucket in prod.
Swapping providers is a config change, not a code change.

Object keys are namespaced by firm so tenants never share a path prefix:
    {firm_id}/cases/{case_id}/{document_id}/{filename}
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    """Create the configured bucket if it does not exist (idempotent)."""
    client = _client()
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in existing:
        client.create_bucket(Bucket=settings.s3_bucket)
        logger.info("created_bucket", bucket=settings.s3_bucket)


def build_key(firm_id: uuid.UUID, case_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    return f"{firm_id}/cases/{case_id}/{document_id}/{filename}"


def upload_fileobj(fileobj: BinaryIO, key: str, content_type: str | None = None) -> str:
    extra = {"ContentType": content_type} if content_type else {}
    _client().upload_fileobj(fileobj, settings.s3_bucket, key, ExtraArgs=extra or None)
    logger.info("uploaded_object", key=key)
    return key


def download_fileobj(key: str, fileobj: BinaryIO) -> None:
    _client().download_fileobj(settings.s3_bucket, key, fileobj)


def presigned_get_url(key: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
