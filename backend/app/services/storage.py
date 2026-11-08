"""
Cloudflare R2 Storage Service
"""
import os
import uuid
from typing import Optional
from datetime import datetime, timezone
import boto3
from botocore.client import Config

from app.core.config import get_settings

settings = get_settings()


class R2Storage:
    """Cloudflare R2 compatible S3 storage client."""
    
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        self.bucket = settings.R2_BUCKET_NAME
        self.public_domain = settings.R2_PUBLIC_DOMAIN.rstrip("/") if settings.R2_PUBLIC_DOMAIN else ""
    
    def upload_file(self, local_path: str, object_key: str, content_type: str = "application/octet-stream") -> str:
        """Upload a file to R2 and return the public URL."""
        self.s3_client.upload_file(
            local_path,
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
        return self.get_public_url(object_key)
    
    def upload_bytes(self, data: bytes, object_key: str, content_type: str = "application/octet-stream") -> str:
        """Upload raw bytes to R2 and return the public URL."""
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
        return self.get_public_url(object_key)
    
    def get_public_url(self, object_key: str) -> str:
        """Get public URL for an object."""
        if self.public_domain:
            return f"{self.public_domain}/{object_key}"
        return f"{settings.R2_ENDPOINT_URL}/{self.bucket}/{object_key}"
    
    def delete_file(self, object_key: str) -> bool:
        """Delete a file from R2."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=object_key)
            return True
        except Exception:
            return False
    
    def get_presigned_url(self, object_key: str, expiration: int = 3600) -> str:
        """Get a presigned URL for temporary access."""
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expiration,
        )
    
    def generate_object_key(self, user_id: str, filename: str, folder: str = "outputs") -> str:
        """Generate a unique object key."""
        ext = filename.split(".")[-1] if "." in filename else "mp4"
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{folder}/{user_id}/{timestamp}_{unique_id}.{ext}"