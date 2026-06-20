import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { fetchImageBlobViaProxy } from "../../api/chat-api";
import { useTranslation } from "../../i18n/language-context";

type Tool = "pen" | "eraser";

interface Point {
  x: number;
  y: number;
}

// 캔버스(원본 해상도) 좌표 기준으로 저장하므로, 같은 사진을 다시 열면
// 화면 크기와 무관하게 동일하게 재생되어 비파괴 편집이 가능하다.
export interface Stroke {
  tool: Tool;
  color: string;
  width: number; // 캔버스 픽셀 기준 두께
  points: Point[];
}

interface PetPhotoEditorProps {
  open: boolean;
  imageSrc: string;
  initialStrokes?: Stroke[];
  saving?: boolean;
  onCancel: () => void;
  onSave: (blob: Blob, strokes: Stroke[]) => void;
}

// 캔버스 해상도 상한 — 원본이 커도 이 안으로 축소해 메모리/용량을 제어한다.
const MAX_DIM = 1024;

const COLORS = [
  "#EF4444",
  "#F59E0B",
  "#FACC15",
  "#22C55E",
  "#3B82F6",
  "#8B5CF6",
  "#EC4899",
  "#111827",
  "#FFFFFF",
];

const THICKNESS = { min: 2, max: 36 };

// 브러시/지우개 크기에 맞춰 원형 커서를 SVG로 만든다. 화면상 브러시 지름은
// thickness(px)와 같으므로 커서 지름도 동일하게 맞춘다. 핫스팟은 원의 중심.
const cursorFor = (tool: Tool, color: string, thickness: number): string => {
  const diameter = Math.max(6, Math.min(thickness, 96));
  const size = diameter + 4;
  const center = size / 2;
  const radius = diameter / 2;
  const ring = tool === "eraser" ? "#6B7280" : color;
  const dash = tool === "eraser" ? ' stroke-dasharray="3 3"' : "";
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">` +
    `<circle cx="${center}" cy="${center}" r="${radius + 0.75}" fill="none" stroke="rgba(0,0,0,0.45)" stroke-width="1"/>` +
    `<circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="${ring}" stroke-width="1.5"${dash}/>` +
    `</svg>`;
  const encoded = encodeURIComponent(svg)
    .replace(/'/g, "%27")
    .replace(/"/g, "%22");
  return `url("data:image/svg+xml,${encoded}") ${center} ${center}, crosshair`;
};

const loadImg = (src: string, crossOrigin: boolean): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image();
    if (crossOrigin) {
      img.crossOrigin = "anonymous";
    }
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });

interface LoadedImage {
  image: HTMLImageElement;
  exportable: boolean; // 캔버스 오염 없이 저장(toBlob) 가능한지
  revoke: () => void;
}

// 원격 이미지는 fetch→blob→objectURL 경로가 가장 확실하다. 같은 출처 blob이라
// 캔버스가 절대 오염되지 않아 저장이 보장된다. 실패 시 crossOrigin/일반 로드로
// 폴백하며, 일반 로드는 표시만 되고 저장은 막힐 수 있다(exportable=false).
const loadEditableImage = async (src: string): Promise<LoadedImage> => {
  if (src.startsWith("blob:") || src.startsWith("data:")) {
    return { image: await loadImg(src, false), exportable: true, revoke: () => {} };
  }

  // 1순위: 동일 출처 백엔드 프록시. 원격(S3/CloudFront)이 브라우저 origin에 CORS
  // 헤더를 주지 않아도 같은 출처 blob이라 캔버스가 절대 오염되지 않아 저장이 보장된다.
  // (기존 펫 수정 시 저장 실패의 근본 원인 — CloudFront 직접 fetch의 CORS 의존 제거.)
  try {
    const objectUrl = URL.createObjectURL(await fetchImageBlobViaProxy(src));
    const image = await loadImg(objectUrl, false);
    return { image, exportable: true, revoke: () => URL.revokeObjectURL(objectUrl) };
  } catch {
    // 프록시 실패(구버전 백엔드 등) 시 아래 CORS 경로로 폴백.
  }

  // 미리보기 <img>가 CORS 없이 캐시해둔 응답을 재사용하지 않도록 캐시 키를 분리한다.
  // (읽기 URL은 서명되지 않으므로 파라미터 추가가 안전하다.)
  const corsSrc = src + (src.includes("?") ? "&" : "?") + "cors=1";

  try {
    const response = await fetch(corsSrc, { mode: "cors", credentials: "omit" });
    if (response.ok) {
      const objectUrl = URL.createObjectURL(await response.blob());
      const image = await loadImg(objectUrl, false);
      return { image, exportable: true, revoke: () => URL.revokeObjectURL(objectUrl) };
    }
  } catch {
    // 아래 폴백으로 진행
  }

  try {
    return { image: await loadImg(corsSrc, true), exportable: true, revoke: () => {} };
  } catch {
    // 표시는 되지만 캔버스가 오염되어 저장이 막힐 수 있다.
    return { image: await loadImg(src, false), exportable: false, revoke: () => {} };
  }
};

// 점들을 부드러운 곡선(quadratic)으로 이어 손그림을 매끄럽게 한다.
const paintStroke = (ctx: CanvasRenderingContext2D, stroke: Stroke) => {
  const { points, tool, color, width } = stroke;
  if (points.length === 0) {
    return;
  }

  ctx.save();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.lineWidth = width;
  ctx.globalCompositeOperation =
    tool === "eraser" ? "destination-out" : "source-over";
  ctx.strokeStyle = color;
  ctx.fillStyle = color;

  if (points.length === 1) {
    ctx.beginPath();
    ctx.arc(points[0].x, points[0].y, width / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    return;
  }

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length - 1; i += 1) {
    const mid = {
      x: (points[i].x + points[i + 1].x) / 2,
      y: (points[i].y + points[i + 1].y) / 2,
    };
    ctx.quadraticCurveTo(points[i].x, points[i].y, mid.x, mid.y);
  }
  const last = points[points.length - 1];
  ctx.lineTo(last.x, last.y);
  ctx.stroke();
  ctx.restore();
};

const PetPhotoEditor = ({
  open,
  imageSrc,
  initialStrokes,
  saving = false,
  onCancel,
  onSave,
}: PetPhotoEditorProps) => {
  const { t } = useTranslation();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null); // 그림 레이어(오프스크린)
  const strokesRef = useRef<Stroke[]>([]);
  // 되돌리기 히스토리: 각 변경(획 추가/전체 지우기) 직전의 strokes 스냅샷을 쌓아,
  // 전체 지우기까지 한 단계씩 되돌릴 수 있게 한다.
  const historyRef = useRef<Stroke[][]>([]);
  const drawingRef = useRef<Stroke | null>(null);
  const revokeRef = useRef<() => void>(() => {});
  // 최신 initialStrokes를 reload 트리거 없이 참조하기 위한 ref.
  const initialStrokesRef = useRef(initialStrokes);
  initialStrokesRef.current = initialStrokes;

  const [tool, setTool] = useState<Tool>("pen");
  const [color, setColor] = useState(COLORS[0]);
  const [thickness, setThickness] = useState(6);
  const [canUndo, setCanUndo] = useState(false); // 되돌릴 히스토리가 있는지
  const [hasStrokes, setHasStrokes] = useState(false); // 지울 그림이 있는지
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState(false);

  // 사진 위에 그림 레이어를 합성해 화면 캔버스에 그린다.
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const image = imageRef.current;
    const overlay = overlayRef.current;
    if (!canvas || !image || !overlay) {
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    ctx.drawImage(overlay, 0, 0);
  }, []);

  // 저장된 strokes(+ 진행 중인 stroke)를 그림 레이어에 다시 그린다.
  const redrawOverlay = useCallback(() => {
    const overlay = overlayRef.current;
    if (!overlay) {
      return;
    }
    const ctx = overlay.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    strokesRef.current.forEach((stroke) => paintStroke(ctx, stroke));
    if (drawingRef.current) {
      paintStroke(ctx, drawingRef.current);
    }
    render();
  }, [render]);

  useEffect(() => {
    if (!open || !imageSrc) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setLoadError(false);
    setSaveError(false);
    // 이전에 그린 stroke를 복원(깊은 복사)해 비파괴 편집을 가능하게 한다.
    strokesRef.current = (initialStrokesRef.current ?? []).map((stroke) => ({
      ...stroke,
      points: stroke.points.map((point) => ({ ...point })),
    }));
    drawingRef.current = null;
    // 복원된 그림은 이번 세션의 시작 상태이므로 되돌리기 히스토리는 비운다.
    // (지우기는 그림이 있으면 가능, 되돌리기는 이번 세션 편집이 있어야 가능)
    historyRef.current = [];
    setCanUndo(false);
    setHasStrokes(strokesRef.current.length > 0);

    loadEditableImage(imageSrc)
      .then(({ image, revoke }) => {
        if (cancelled) {
          revoke();
          return;
        }
        revokeRef.current = revoke;
        const scale = Math.min(1, MAX_DIM / Math.max(image.width, image.height));
        const width = Math.max(1, Math.round(image.width * scale));
        const height = Math.max(1, Math.round(image.height * scale));

        const canvas = canvasRef.current;
        if (!canvas) {
          return;
        }
        canvas.width = width;
        canvas.height = height;

        const overlay = document.createElement("canvas");
        overlay.width = width;
        overlay.height = height;
        overlayRef.current = overlay;
        imageRef.current = image;

        setIsLoading(false);
        redrawOverlay(); // 복원된 stroke까지 함께 그린다.
      })
      .catch(() => {
        if (!cancelled) {
          setIsLoading(false);
          setLoadError(true);
        }
      });

    return () => {
      cancelled = true;
      revokeRef.current();
      revokeRef.current = () => {};
    };
  }, [open, imageSrc, redrawOverlay]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onCancel]);

  const toCanvasPoint = (event: ReactPointerEvent<HTMLCanvasElement>): Point => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (isLoading || loadError) {
      return;
    }
    event.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    canvas.setPointerCapture(event.pointerId);
    // 화면 표시 크기 대비 캔버스 해상도 배율을 곱해, 이미지 크기와 무관하게
    // 화면상 두께가 일정하게 보이도록 한다.
    const rect = canvas.getBoundingClientRect();
    const scale = canvas.width / rect.width;
    drawingRef.current = {
      tool,
      color,
      width: thickness * scale,
      points: [toCanvasPoint(event)],
    };
    redrawOverlay();
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) {
      return;
    }
    event.preventDefault();
    drawingRef.current.points.push(toCanvasPoint(event));
    redrawOverlay();
  };

  // 변경 직전의 strokes를 깊은 복사로 히스토리에 쌓는다.
  const pushHistory = () => {
    historyRef.current.push(
      strokesRef.current.map((stroke) => ({
        ...stroke,
        points: stroke.points.map((point) => ({ ...point })),
      })),
    );
    setCanUndo(true);
  };

  const finishStroke = () => {
    if (!drawingRef.current) {
      return;
    }
    pushHistory();
    strokesRef.current.push(drawingRef.current);
    drawingRef.current = null;
    setHasStrokes(true);
    redrawOverlay();
  };

  const handleUndo = () => {
    const previous = historyRef.current.pop();
    if (!previous) {
      return;
    }
    strokesRef.current = previous;
    drawingRef.current = null;
    setCanUndo(historyRef.current.length > 0);
    setHasStrokes(strokesRef.current.length > 0);
    redrawOverlay();
  };

  const handleClear = () => {
    if (strokesRef.current.length === 0) {
      return;
    }
    // 전체 지우기도 되돌릴 수 있도록 직전 상태를 히스토리에 남긴다.
    pushHistory();
    strokesRef.current = [];
    drawingRef.current = null;
    setHasStrokes(false);
    redrawOverlay();
  };

  const handleSave = () => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    setSaveError(false);
    render();
    // 캔버스가 오염(taint)된 경우 toBlob은 동기적으로 SecurityError를 던진다.
    // 잡지 않으면 클릭이 조용히 죽으므로(버튼이 안 눌리는 것처럼 보임) 반드시 감싼다.
    try {
      canvas.toBlob(
        (blob) => {
          if (blob) {
            onSave(blob, strokesRef.current);
          } else {
            setSaveError(true);
          }
        },
        "image/jpeg",
        0.92,
      );
    } catch {
      setSaveError(true);
    }
  };

  if (!open) {
    return null;
  }

  const toolButtonClass = (active: boolean) =>
    [
      "flex h-10 items-center gap-1.5 rounded-xl px-3 text-sm font-bold transition-all",
      active
        ? "bg-[#2F6F67] text-white shadow-sm"
        : "bg-[#F8FAFC] text-[#6B7280] hover:bg-[#E5E7EB]",
    ].join(" ");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1F2937]/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden rounded-[1.75rem] bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#E5E7EB] px-5 py-4">
          <h2 className="text-base font-extrabold text-[#1F2937]">
            {t("pet.decorateTitle")}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label={t("common.cancel")}
            className="flex h-8 w-8 items-center justify-center rounded-full text-[#6B7280] transition hover:bg-[#F8FAFC]"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="relative mx-auto flex min-h-[240px] items-center justify-center rounded-2xl bg-[#F8FAFC] ring-1 ring-[#E5E7EB]">
            {isLoading ? (
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-teal-100 border-t-teal-700" />
            ) : loadError ? (
              <p className="px-6 py-10 text-center text-sm font-bold text-red-500">
                {t("pet.decorateLoadError")}
              </p>
            ) : null}
            <canvas
              ref={canvasRef}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={finishStroke}
              onPointerLeave={finishStroke}
              onPointerCancel={finishStroke}
              className={`max-h-[52dvh] max-w-full rounded-2xl ${
                isLoading || loadError ? "hidden" : "block"
              }`}
              style={{
                touchAction: "none",
                cursor: cursorFor(tool, color, thickness),
              }}
            />
          </div>

          <p className="mt-3 text-center text-xs font-semibold text-[#6B7280]">
            {t("pet.decorateHint")}
          </p>

          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setTool("pen")}
                className={toolButtonClass(tool === "pen")}
              >
                ✏️ {t("pet.decoratePen")}
              </button>
              <button
                type="button"
                onClick={() => setTool("eraser")}
                className={toolButtonClass(tool === "eraser")}
              >
                🧽 {t("pet.decorateEraser")}
              </button>
              <button
                type="button"
                onClick={handleUndo}
                disabled={!canUndo}
                className={`${toolButtonClass(false)} disabled:cursor-not-allowed disabled:opacity-40`}
              >
                ↩️ {t("pet.decorateUndo")}
              </button>
              <button
                type="button"
                onClick={handleClear}
                disabled={!hasStrokes}
                className={`${toolButtonClass(false)} disabled:cursor-not-allowed disabled:opacity-40`}
              >
                🗑️ {t("pet.decorateClear")}
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {COLORS.map((swatch) => (
                <button
                  key={swatch}
                  type="button"
                  aria-label={swatch}
                  onClick={() => {
                    setColor(swatch);
                    setTool("pen");
                  }}
                  className={`h-7 w-7 rounded-full ring-2 ring-offset-2 transition-transform hover:scale-110 ${
                    color === swatch && tool === "pen"
                      ? "ring-[#2F6F67]"
                      : "ring-transparent"
                  }`}
                  style={{
                    backgroundColor: swatch,
                    boxShadow:
                      swatch === "#FFFFFF" ? "inset 0 0 0 1px #E5E7EB" : undefined,
                  }}
                />
              ))}
            </div>

            <div className="flex items-center gap-3">
              <span className="text-sm font-bold text-[#6B7280]">
                {t("pet.decorateThickness")}
              </span>
              <input
                type="range"
                min={THICKNESS.min}
                max={THICKNESS.max}
                value={thickness}
                onChange={(event) => setThickness(Number(event.target.value))}
                className="h-2 flex-1 cursor-pointer accent-[#2F6F67]"
              />
              <span
                className="rounded-full bg-[#2F6F67]"
                style={{
                  width: `${thickness}px`,
                  height: `${thickness}px`,
                  minWidth: `${THICKNESS.min}px`,
                  minHeight: `${THICKNESS.min}px`,
                }}
              />
            </div>
          </div>
        </div>

        {saveError ? (
          <p className="border-t border-red-100 bg-red-50/80 px-5 py-3 text-center text-xs font-bold text-red-600">
            {t("pet.decorateSaveError")}
          </p>
        ) : (
          <p className="flex items-start gap-1.5 border-t border-amber-100 bg-amber-50/70 px-5 py-3 text-xs font-semibold text-amber-700">
            <span aria-hidden="true">⚠️</span>
            <span>{t("pet.decorateApplyNotice")}</span>
          </p>
        )}

        <div className="flex justify-end gap-3 border-t border-[#E5E7EB] px-5 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="h-11 min-w-24 rounded-xl border border-[#E5E7EB] bg-[#F8FAFC] px-6 text-sm font-extrabold text-[#6B7280] transition hover:bg-[#E5E7EB]"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || isLoading || loadError}
            className="inline-flex h-11 min-w-28 items-center justify-center rounded-xl bg-[#2F6F67] px-6 text-sm font-extrabold text-white transition hover:bg-[#255E57] disabled:cursor-not-allowed disabled:bg-[#E5E7EB] disabled:text-[#6B7280]"
          >
            {saving ? t("pet.decorateSaving") : t("pet.decorateSave")}
          </button>
        </div>
      </div>
    </div>
  );
};

export default PetPhotoEditor;
