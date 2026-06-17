import { FileText, Play, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import type { EmrResult } from "../../types/emr";
import { Panel } from "./EmrShared";

// 영상 첨부 — URL 확장자로 영상/이미지 구분
const isVideoUrl = (url: string) => /\.(mp4|mov|webm|avi)(\?|$)/i.test(url);

export function IntakePanel({
  emr,
  visibleFiles,
  hiddenFileCount,
  onApplyIntake,
  onPreviewImage,
  isReadOnly = false,
  followupContent,
}: {
  emr: EmrResult;
  visibleFiles: string[];
  hiddenFileCount: number;
  onApplyIntake: (target: "summary" | "memo" | "all") => void;
  onPreviewImage: (url: string, label: string) => void;
  isReadOnly?: boolean;
  followupContent?: ReactNode;
}) {
  const summary = emr.triage_summary.summary;
  const memo = emr.triage_summary.memo;

  return (
    <Panel className="flex flex-1 min-h-0 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center px-4 py-2.5">
        <h2 className="text-base font-extrabold text-slate-900">
          사전 문진 / 메모
        </h2>
      </div>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto overscroll-contain px-4 pb-3">
        <button
          type="button"
          onClick={() => onApplyIntake("all")}
          disabled={isReadOnly}
          className="h-9 w-full rounded-lg border border-blue-700 bg-blue-600 text-xs font-extrabold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400 disabled:shadow-none"
        >
          사전문진 + 메모 전체 옮기기
        </button>

        <div className="rounded-lg border border-blue-200 bg-blue-50 p-2.5 shadow-sm">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-sm font-extrabold text-slate-800">
              <Sparkles className="h-4 w-4 text-blue-500" strokeWidth={2.2} />
              AI 요약 문진
            </p>
            <button
              type="button"
              onClick={() => onApplyIntake("summary")}
              disabled={summary.length === 0 || isReadOnly}
              className="rounded-md border border-blue-600 bg-blue-600 px-2 py-1 text-xs font-extrabold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-100 disabled:text-slate-400 disabled:shadow-none"
            >
              옮기기
            </button>
          </div>
          {summary.length > 0 ? (
            <ul className="space-y-1.5 text-xs font-bold leading-5 text-slate-600">
              {summary.map((bullet) => (
                <li key={bullet} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs font-bold text-slate-400">
              예약 사전문진 내용이 없습니다.
            </p>
          )}
        </div>

        <div className="rounded-lg border border-blue-200 bg-blue-50 p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-sm font-extrabold text-slate-800">
              <FileText className="h-4 w-4 text-blue-500" strokeWidth={2.2} />
              메모
            </p>
            <button
              type="button"
              onClick={() => onApplyIntake("memo")}
              disabled={!memo || isReadOnly}
              className="rounded-md border border-blue-600 bg-blue-600 px-2 py-1 text-xs font-extrabold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-100 disabled:text-slate-400 disabled:shadow-none"
            >
              옮기기
            </button>
          </div>
          <p className="text-xs font-bold leading-5 text-slate-600">
            {memo ?? "수의사 메모가 없습니다."}
          </p>
        </div>

        {followupContent}

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-xs font-extrabold text-slate-800">
              첨부 파일
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {visibleFiles.length === 0 && (
              <div className="w-full rounded-lg bg-slate-50 px-3 py-3 text-center text-xs font-bold text-slate-400">
                보호자 첨부 파일 없음
              </div>
            )}
            {visibleFiles.map((fileUrl, index) => (
              <button
                type="button"
                key={fileUrl}
                onClick={() => onPreviewImage(fileUrl, `보호자 첨부 ${index + 1}`)}
                className="relative h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-slate-100"
              >
                {/* 영상 첨부 — 영상은 미리보기 프레임 + 재생 아이콘, 클릭 시 모달에서 재생 */}
                {isVideoUrl(fileUrl) ? (
                  <>
                    <video
                      src={fileUrl}
                      className="h-full w-full object-cover"
                      muted
                      playsInline
                      preload="metadata"
                    />
                    <span className="absolute inset-0 flex items-center justify-center bg-slate-900/25">
                      <Play className="h-5 w-5 text-white drop-shadow" fill="currentColor" />
                    </span>
                  </>
                ) : (
                  <img
                    src={fileUrl}
                    alt={`보호자 첨부 ${index + 1}`}
                    className="h-full w-full object-cover"
                  />
                )}
                {index === 3 && hiddenFileCount > 0 && (
                  <div className="absolute inset-0 flex items-center justify-center bg-slate-800/55 text-sm font-extrabold text-white">
                    +{hiddenFileCount}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Panel>
  );
}
