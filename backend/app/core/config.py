from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # 모든 항목에 안전한 기본값을 둬서, .env가 비어 있어도 backend가 일단 뜬다.
    # (S3/OpenAI 등 외부 연동은 값이 비면 "실제로 호출할 때만" 막힘 → 로컬 UI 개발은 가능)
    # docker-compose 는 DATABASE_URL/SECRET_KEY 등을 environment 로 덮어쓴다.

    # Database
    DATABASE_URL: str = "postgresql://medipaw:medipaw_secret@localhost:5432/medipaw"

    # JWT
    SECRET_KEY: str = "dev-secret-change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # AWS S3 (비우면 S3 업로드/조회 기능만 비활성)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str = "medipaw-bucket"
    CLOUDFRONT_URL: Optional[str] = ""

    # OpenAI (비우면 AI 기능만 비활성)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"
    OPENAI_VISION_MODEL: str = "gpt-5.4-mini"

    # 서버 설정 — 운영 안전 기본값. 로컬 개발 시 .env에서 DEBUG=true 로 오버라이드.
    DEBUG: bool = False
    # 콤마 구분 origins 문자열. docker-compose.yml 또는 .env에서 오버라이드 가능.
    ALLOWED_ORIGINS: str = (
        "http://localhost:5173,http://localhost:5174,"
        "http://127.0.0.1:5173,"
        "http://192.168.0.2:5173,http://192.168.0.32:5173,"
        "http://192.168.0.11:5173,http://192.168.0.2:5174"
    )

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
