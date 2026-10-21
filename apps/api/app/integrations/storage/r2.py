import asyncio

import boto3
from botocore.config import Config

from app.config import get_settings
from app.integrations.storage.base import StorageProvider


class R2Storage(StorageProvider):
    """S3-compatible storage (Cloudflare R2 in cloud, MinIO locally)."""

    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.storage_bucket
        self.s3 = boto3.client(
            "s3",
            endpoint_url=s.storage_endpoint,
            aws_access_key_id=s.storage_access_key,
            aws_secret_access_key=s.storage_secret_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        await asyncio.to_thread(self.s3.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.s3.head_object, Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def presign_get(self, key: str, expires_s: int = 900) -> str:
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_s
        )

    def presign_put(self, key: str, expires_s: int = 900) -> str:
        return self.s3.generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_s
        )

    def create_multipart(self, key: str, parts: int, expires_s: int = 3600) -> dict:
        up = self.s3.create_multipart_upload(Bucket=self.bucket, Key=key)
        urls = [
            self.s3.generate_presigned_url(
                "upload_part",
                Params={"Bucket": self.bucket, "Key": key, "UploadId": up["UploadId"], "PartNumber": i + 1},
                ExpiresIn=expires_s,
            )
            for i in range(parts)
        ]
        return {"upload_id": up["UploadId"], "part_urls": urls}
