import type { ChangeEvent, RefObject } from "react";

import { useTranslation } from "../../i18n/language-context";

// PawIcon removed

const CameraIcon = () => (
  <svg
    viewBox="0 0 24 24"
    aria-hidden="true"
    className="h-5 w-5"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
  >
    <path d="M4 8h3l1.5-2h7L17 8h3v10H4V8Z" />
    <path d="M9 13a3 3 0 1 0 6 0 3 3 0 0 0-6 0Z" />
  </svg>
);

interface PetImageUploaderProps {
  previewUrl: string;
  isDetailMode: boolean;
  fileInputRef: RefObject<HTMLInputElement>;
  onImageChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onDecorate?: () => void;
  errorMessage?: string;
}

const BrushIcon = () => (
  <svg
    viewBox="0 0 24 24"
    aria-hidden="true"
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9.5 14.5 4 20l.5-3.5L15 6l3 3-10.5 5.5Z" />
    <path d="M15 6l2-2a1.5 1.5 0 0 1 2 2l-2 2" />
  </svg>
);

const PetImageUploader = ({
  previewUrl,
  isDetailMode,
  fileInputRef,
  onImageChange,
  onDecorate,
  errorMessage,
}: PetImageUploaderProps) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center justify-center mb-6 mt-2 md:mb-10 md:mt-4">
      <div className="relative group">
        <button
          type="button"
          onClick={() => {
            if (!isDetailMode) {
              fileInputRef.current?.click();
            }
          }}
          className={`relative flex h-32 w-32 md:h-40 md:w-40 items-center justify-center overflow-hidden rounded-[2rem] md:rounded-[2.5rem] bg-[#F8FAFC] ring-1 ring-[#E5E7EB] transition-all duration-300 ${
            isDetailMode
              ? "cursor-default"
              : "hover:ring-[#2F6F67]/50"
          }`}
        >
          {previewUrl ? (
            <img
              src={previewUrl}
              alt={t("pet.photoPreviewAlt")}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex flex-col items-center justify-center text-[#6B7280] transition-colors duration-300 group-hover:text-[#2F6F67]">
              <CameraIcon />
              <span className="mt-2 text-xs font-bold">
                {t("pet.photoUpload")}
              </span>
            </div>
          )}
          {!isDetailMode && previewUrl && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#1F2937]/30 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
              <CameraIcon />
            </div>
          )}
        </button>
        {!isDetailMode && !previewUrl && (
          <div className="absolute -bottom-2 -right-2 flex h-12 w-12 md:h-14 md:w-14 items-center justify-center rounded-2xl bg-white shadow-lg ring-1 ring-[#E5E7EB] overflow-hidden transition-transform duration-300 group-hover:scale-105">
            <img
              src="/assets/profile1.png"
              alt=""
              className="h-full w-full object-cover"
            />
          </div>
        )}
      </div>
      
      {!isDetailMode && previewUrl && onDecorate ? (
        <button
          type="button"
          onClick={onDecorate}
          className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-[#E5E7EB] bg-white px-4 py-2 text-xs font-bold text-[#2F6F67] shadow-sm transition-all hover:border-[#2F6F67]/40 hover:bg-[#2F6F67]/5"
        >
          <BrushIcon />
          {t("pet.decorate")}
        </button>
      ) : null}

      <div className="mt-6 text-center">
        <p className="text-sm font-medium text-slate-500">
          {t("pet.photoHint")}
        </p>
        {errorMessage ? (
          <p className="mt-2 text-xs font-bold text-red-500 bg-red-50 py-1 px-3 rounded-full inline-block animate-pulse">{errorMessage}</p>
        ) : null}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png"
        onChange={onImageChange}
        disabled={isDetailMode}
        className="hidden"
      />
    </div>
  );
};

export default PetImageUploader;
