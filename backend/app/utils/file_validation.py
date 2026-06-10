from fastapi import HTTPException


def validate_file(
    content_type: str,
    file_size: int,
    allowed_types: list[str],
    max_bytes: int,
) -> None:
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="허용되지 않는 파일 형식입니다.")
    mb = max_bytes // (1024 * 1024)
    if file_size > max_bytes:
        raise HTTPException(status_code=413, detail=f"파일 크기는 {mb}MB 이하만 업로드 가능합니다.")
