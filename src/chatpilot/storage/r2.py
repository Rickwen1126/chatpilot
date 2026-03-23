"""Cloudflare R2 storage — S3-compatible object storage for media."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

import boto3

logger = logging.getLogger(__name__)


class R2Storage:
    """Upload files to Cloudflare R2 and return public URLs."""

    def __init__(self) -> None:
        self._endpoint = os.environ.get("R2_ENDPOINT", "")
        self._bucket = os.environ.get("R2_BUCKET", "chatpilot-media")
        self._public_url = os.environ.get("R2_PUBLIC_URL", "")
        self._client = None

        if self._endpoint:
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
                aws_secret_access_key=os.environ.get(
                    "R2_SECRET_ACCESS_KEY", ""
                ),
                region_name="auto",
            )
            logger.info("R2Storage initialized: %s/%s", self._endpoint, self._bucket)
        else:
            logger.warning("R2Storage not configured (missing R2_ENDPOINT)")

    @property
    def available(self) -> bool:
        return self._client is not None

    async def upload(
        self,
        data: bytes,
        content_type: str = "image/jpeg",
        extension: str = "jpg",
    ) -> str | None:
        """Upload bytes to R2, return public URL."""
        if not self._client:
            logger.warning("R2 not configured, cannot upload")
            return None

        filename = f"{uuid.uuid4().hex}.{extension}"

        def _do_upload():
            self._client.put_object(
                Bucket=self._bucket,
                Key=filename,
                Body=data,
                ContentType=content_type,
            )

        await asyncio.to_thread(_do_upload)

        url = f"{self._public_url}/{filename}"
        logger.info("Uploaded to R2: %s (%d bytes)", url, len(data))
        return url
