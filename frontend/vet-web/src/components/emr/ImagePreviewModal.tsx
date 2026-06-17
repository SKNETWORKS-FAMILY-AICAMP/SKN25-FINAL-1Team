import { X } from "lucide-react";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";

// 영상 첨부 — URL 확장자로 영상/이미지 구분
const isVideoUrl = (url: string) => /\.(mp4|mov|webm|avi)(\?|$)/i.test(url);

export function ImagePreviewModal({
  image,
  onClose,
}: {
  image: { url: string; label: string };
  onClose: () => void;
}) {
  useEscapeToClose(onClose);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 px-4">
      <div className="w-full max-w-[760px] rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-extrabold text-slate-900">
            {image.label}
          </h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <X className="h-5 w-5 text-slate-600" />
          </button>
        </div>
        <div className="bg-slate-950 p-4">
          {/* 영상 첨부 — 영상이면 컨트롤 달린 플레이어로 재생 */}
          {isVideoUrl(image.url) ? (
            <video
              src={image.url}
              controls
              autoPlay
              playsInline
              className="mx-auto max-h-[70vh] rounded-lg object-contain"
            />
          ) : (
            <img
              src={image.url}
              alt={image.label}
              className="mx-auto max-h-[70vh] rounded-lg object-contain"
            />
          )}
        </div>
      </div>
    </div>
  );
}
