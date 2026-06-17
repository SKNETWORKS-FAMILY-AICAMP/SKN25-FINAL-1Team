"""영상 프레임 추출 — 업로드된 영상에서 선명한 프레임 몇 장을 뽑아 CNN 입력으로 쓴다.

cv2.VideoCapture는 파일 경로만 받으므로 bytes를 임시 파일로 떨군 뒤 읽는다.
추출된 프레임은 CNN(analyze_skin/analyze_eye)이 바로 디코딩할 수 있도록 JPEG bytes로 인코딩해 반환.
"""
from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger(__name__)


# 영상 판정 — Laplacian 분산으로 선명도 측정(흐릿한 프레임 거르기)
def _sharpness(frame) -> float:
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


# 영상 판정 — 영상 bytes → 균등 샘플 후 선명한 순 JPEG 프레임 목록
def extract_frames(video_bytes: bytes, count: int = 5) -> list[bytes]:
    import cv2

    # bytes를 임시 파일로 저장(VideoCapture가 경로만 받음)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            return []

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        if total <= 0:
            cap.release()
            return []

        # 영상 전체를 균등 간격으로 count*2장 샘플 → 그중 선명한 count장 선택
        sample_n = min(total, max(count * 2, count))
        positions = [int(total * i / sample_n) for i in range(sample_n)]

        scored: list[tuple[float, bytes]] = []
        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                scored.append((_sharpness(frame), buf.tobytes()))

        cap.release()

        # 선명도 높은 순 count장
        scored.sort(key=lambda x: x[0], reverse=True)
        return [jpg for _, jpg in scored[:count]]

    except Exception as exc:
        logger.warning("[VideoFrame] 프레임 추출 실패: %s", exc)
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
