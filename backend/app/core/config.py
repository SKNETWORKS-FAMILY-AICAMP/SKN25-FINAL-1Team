from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional

_DEFAULT_SECRET_KEY = "dev-secret-change-me-in-production"


class Settings(BaseSettings):
    # 모든 항목에 안전한 기본값을 둬서, .env가 비어 있어도 backend가 일단 뜬다.
    # (S3/OpenAI 등 외부 연동은 값이 비면 "실제로 호출할 때만" 막힘 → 로컬 UI 개발은 가능)
    # docker-compose 는 DATABASE_URL/SECRET_KEY 등을 environment 로 덮어쓴다.

    # Database
    DATABASE_URL: str = "postgresql://medipaw:medipaw_secret@localhost:5432/medipaw"

    # JWT
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # AWS S3 (비우면 S3 업로드/조회 기능만 비활성)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str = "medipaw-images"
    CLOUDFRONT_URL: Optional[str] = ""

    # OpenAI (비우면 AI 기능만 비활성)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"
    OPENAI_VISION_MODEL: str = "gpt-5.4-mini"
    # 이미지 분석에서 피부/안구 CNN 사용 여부. false면 OpenAI vision 관찰만 사용(실험용).
    USE_CNN_VISION: bool = True

    # STT (Groq Whisper — 음성 입력 전사)
    GROQ_API_KEY: str = ""
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"

    # SMTP 이메일 발송
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    CS_EMAIL: str = ""

    # 서버 설정 — 운영 안전 기본값. 로컬 개발 시 .env에서 DEBUG=true 로 오버라이드.
    DEBUG: bool = False
    # 콤마 구분 origins 문자열. docker-compose.yml 또는 .env에서 오버라이드 가능.
    ALLOWED_ORIGINS: str = (
        "http://localhost:5173,http://localhost:5174,"
        "http://127.0.0.1:5173,"
        "http://192.168.0.2:5173,http://192.168.0.32:5173,"
        "http://192.168.0.11:5173,http://192.168.0.2:5174"
    )

    @model_validator(mode="after")
    def _warn_default_secret_in_prod(self) -> "Settings":
        # 운영(DEBUG=False)에서 기본 SECRET_KEY 로 뜨면 JWT 위조가 가능하다.
        # 단, 하드 실패는 prod compose 의 `${SECRET_KEY:?}` 가 책임진다(미설정 시 컨테이너 자체가 안 뜸).
        # 여기서 raise 하면 .env 없는 로컬/테스트 실행까지 죽으므로, 코드 레벨은 '큰 경고'까지만 한다.
        if not self.DEBUG and self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            import warnings
            warnings.warn(
                "SECRET_KEY 가 기본 개발용 키입니다(DEBUG=false). 운영 배포라면 즉시 교체하세요 — "
                "기본키로는 JWT 위조가 가능합니다.",
                stacklevel=2,
            )
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
