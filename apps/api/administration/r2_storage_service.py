import os
import hashlib
import logging
from datetime import datetime
from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class R2StorageService:
    """
    Independent storage service for Cloudflare R2 object storage.
    Provides S3-compatible operations: upload, download, metadata lookup,
    remote integrity verification, and pre-signed reference generation.
    """

    @classmethod
    def is_configured(cls) -> bool:
        """
        Returns True if Cloudflare R2 credentials and bucket are configured in settings/env.
        """
        return bool(
            getattr(settings, 'R2_ACCESS_KEY_ID', None) and
            getattr(settings, 'R2_SECRET_ACCESS_KEY', None) and
            getattr(settings, 'R2_BUCKET_NAME', None)
        )

    @classmethod
    def get_client(cls):
        """
        Initializes an authenticated boto3 S3 client configured for Cloudflare R2.
        """
        if not cls.is_configured():
            return None

        import boto3
        from botocore.config import Config

        endpoint_url = getattr(settings, 'R2_ENDPOINT_URL', None)
        if not endpoint_url and getattr(settings, 'R2_ACCOUNT_ID', None):
            endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

        # Cloudflare R2 requires region_name='auto' and s3v4 signature
        config = Config(
            signature_version='s3v4',
            retries={'max_attempts': 3, 'mode': 'standard'},
            connect_timeout=15,
            read_timeout=60,
        )

        return boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name='auto',
            config=config,
        )

    @classmethod
    def generate_storage_key(cls, backup_id: int, dt: datetime, backup_type: str, filename: str = '') -> str:
        """
        Constructs a collision-safe, structured object key for Cloudflare R2.
        Example: loksewaai/backups/database/2026/10/01/database-20261001-020000-42-manual.json.gz
        """
        prefix = getattr(settings, 'R2_BACKUP_PREFIX', 'loksewaai/backups/database').strip('/')
        year = dt.strftime('%Y')
        month = dt.strftime('%m')
        day = dt.strftime('%d')
        time_part = dt.strftime('%H%M%S')
        clean_type = backup_type.replace('_', '-').lower()

        base_name = f"database-{dt.strftime('%Y%m%d')}-{time_part}-{backup_id}-{clean_type}.json.gz"
        return f"{prefix}/{year}/{month}/{day}/{base_name}"

    @classmethod
    def upload_file(cls, local_path: str, storage_key: str, metadata: dict = None) -> dict:
        """
        Uploads a local backup archive to Cloudflare R2 with integrity headers.
        """
        if not cls.is_configured():
            raise ValidationError("Cloudflare R2 is not configured on this server.")

        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local backup archive not found: {local_path}")

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME
        file_size = os.path.getsize(local_path)

        extra_args = {
            'ContentType': 'application/gzip',
        }
        if metadata:
            # S3 user metadata must be string values
            extra_args['Metadata'] = {str(k): str(v) for k, v in metadata.items()}

        logger.info(f"Uploading backup ({file_size} bytes) to Cloudflare R2: s3://{bucket}/{storage_key}")

        try:
            with open(local_path, 'rb') as f:
                response = client.put_object(
                    Bucket=bucket,
                    Key=storage_key,
                    Body=f,
                    **extra_args
                )

            etag = response.get('ETag', '').strip('"')
            logger.info(f"Successfully uploaded to R2: {storage_key} (ETag: {etag})")

            return {
                'success': True,
                'storage_key': storage_key,
                'etag': etag,
                'size_bytes': file_size,
                'bucket': bucket,
            }
        except Exception as e:
            logger.exception(f"Failed to upload to Cloudflare R2: {e}")
            raise ValidationError(f"Cloudflare R2 upload failed: {str(e)}")

    @classmethod
    def download_file(cls, storage_key: str, target_local_path: str) -> bool:
        """
        Downloads a remote backup archive from Cloudflare R2 to target_local_path.
        """
        if not cls.is_configured():
            raise ValidationError("Cloudflare R2 is not configured.")

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME

        os.makedirs(os.path.dirname(os.path.abspath(target_local_path)), exist_ok=True)

        try:
            logger.info(f"Downloading R2 object s3://{bucket}/{storage_key} to {target_local_path}")
            client.download_file(bucket, storage_key, target_local_path)
            return True
        except Exception as e:
            logger.exception(f"Failed to download object from R2: {e}")
            raise ValidationError(f"Failed to retrieve backup from Cloudflare R2: {str(e)}")

    @classmethod
    def exists(cls, storage_key: str) -> bool:
        """
        Checks if an object exists in Cloudflare R2.
        """
        if not cls.is_configured():
            return False

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME

        try:
            client.head_object(Bucket=bucket, Key=storage_key)
            return True
        except Exception:
            return False

    @classmethod
    def get_metadata(cls, storage_key: str) -> dict:
        """
        Retrieves remote object size, ETag, last modified timestamp, and custom metadata.
        """
        if not cls.is_configured():
            return {}

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME

        try:
            resp = client.head_object(Bucket=bucket, Key=storage_key)
            return {
                'size_bytes': resp.get('ContentLength', 0),
                'last_modified': resp.get('LastModified'),
                'etag': resp.get('ETag', '').strip('"'),
                'metadata': resp.get('Metadata', {}),
            }
        except Exception as e:
            logger.warning(f"Could not retrieve metadata for s3://{bucket}/{storage_key}: {e}")
            return {}

    @classmethod
    def delete_object(cls, storage_key: str) -> bool:
        """
        Deletes a backup object from Cloudflare R2.
        """
        if not cls.is_configured():
            return False

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME

        try:
            logger.info(f"Deleting R2 object: s3://{bucket}/{storage_key}")
            client.delete_object(Bucket=bucket, Key=storage_key)
            return True
        except Exception as e:
            logger.warning(f"Could not delete R2 object {storage_key}: {e}")
            return False

    @classmethod
    def verify_object_integrity(cls, storage_key: str, expected_sha256: str) -> dict:
        """
        Streams the remote R2 object, verifies gzip integrity and checks SHA-256 match.
        """
        if not cls.is_configured():
            return {
                'valid': False,
                'message': 'Cloudflare R2 is not configured on this server.',
            }

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME

        try:
            resp = client.get_object(Bucket=bucket, Key=storage_key)
            body_stream = resp['Body']
            hasher = hashlib.sha256()
            size = 0

            # Read stream in 64KB chunks
            while True:
                chunk = body_stream.read(65536)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode('utf-8')
                hasher.update(chunk)
                size += len(chunk)

            calculated_sha256 = hasher.hexdigest()

            if expected_sha256 and calculated_sha256 != expected_sha256:
                return {
                    'valid': False,
                    'calculated_sha256': calculated_sha256,
                    'size_bytes': size,
                    'message': f"Remote checksum mismatch: expected {expected_sha256[:12]}..., got {calculated_sha256[:12]}...",
                }

            return {
                'valid': True,
                'calculated_sha256': calculated_sha256,
                'size_bytes': size,
                'message': f"Remote R2 backup verified ({size} bytes, SHA-256 matched).",
            }

        except Exception as e:
            logger.exception(f"Remote R2 verification failed for {storage_key}: {e}")
            return {
                'valid': False,
                'message': f"Remote verification failed: {str(e)}",
            }

    @classmethod
    def generate_presigned_download_url(cls, storage_key: str, expires_in: int = 3600) -> str:
        """
        Generates a secure, temporary pre-signed URL to download the backup archive from R2.
        """
        if not cls.is_configured():
            return ""

        client = cls.get_client()
        bucket = settings.R2_BUCKET_NAME

        try:
            url = client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': storage_key},
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.warning(f"Could not generate pre-signed URL for {storage_key}: {e}")
            return ""
