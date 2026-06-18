"""S3 presigned URL 발급 유틸.

프론트는 백엔드에서 presigned_url(업로드용)을 받아 S3에 직접 PUT 하고,
DB에는 반환된 cloudfront_url(읽기용 주소)을 저장한다.
EC2에서는 IAM Role, 로컬에서는 .env의 AWS 키를 boto3가 자동으로 사용한다.
"""
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import NoCredentialsError

from app.core.config import settings

# region을 명시해야 서울 리전에서 서명(v4)이 올바르게 동작한다.
_s3 = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    endpoint_url=f"https://s3.{settings.AWS_REGION}.amazonaws.com",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)


def _create_object_key(file_name: str, prefix: str) -> str:
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "bin"
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"{prefix}/{today}/{uuid.uuid4().hex}.{ext}"


def _create_read_url(key: str) -> str:
    cdn = (settings.CLOUDFRONT_URL or "").rstrip("/")
    if cdn:
        return f"{cdn}/{key}"

    return (
        f"https://{settings.S3_BUCKET_NAME}.s3."
        f"{settings.AWS_REGION}.amazonaws.com/{key}"
    )


def _ensure_credentials() -> None:
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise NoCredentialsError()


def create_presigned_put(file_name: str, content_type: str, prefix: str) -> dict:
    """업로드용 presigned PUT URL과 읽기용 URL을 생성한다.

    prefix: S3 키 경로 접두사 (예: "chat", "followup").
    """
    _ensure_credentials()
    key = _create_object_key(file_name, prefix)

    presigned_url = _s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=300,  # 5분
    )

    return {"presigned_url": presigned_url, "cloudfront_url": _create_read_url(key)}


def upload_object(file_name: str, content_type: str, body: bytes, prefix: str) -> dict:
    """백엔드가 직접 S3에 업로드하고 읽기용 URL을 반환한다."""
    _ensure_credentials()
    key = _create_object_key(file_name, prefix)

    _s3.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType=content_type,
    )

    return {"cloudfront_url": _create_read_url(key)}


def _key_from_url(file_url: str) -> str:
    """S3/CloudFront 읽기 URL에서 버킷 내 객체 key를 추출한다."""
    parsed = urlparse(file_url)
    if not parsed.path:
        raise ValueError("파일 URL에서 S3 key를 찾을 수 없습니다.")
    return unquote(parsed.path.lstrip("/"))


def read_object_bytes_from_url(file_url: str) -> bytes:
    """S3/CloudFront 읽기 URL에서 객체 key를 추출해 bytes를 읽는다."""
    _ensure_credentials()

    response = _s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=_key_from_url(file_url))
    return response["Body"].read()


def read_object_from_url(file_url: str) -> dict:
    """읽기 URL의 객체를 bytes + content_type 으로 반환한다(동일 출처 프록시용)."""
    _ensure_credentials()

    response = _s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=_key_from_url(file_url))
    return {
        "body": response["Body"].read(),
        "content_type": response.get("ContentType") or "application/octet-stream",
    }
