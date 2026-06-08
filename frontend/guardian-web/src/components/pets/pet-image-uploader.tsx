import type { ChangeEvent, RefObject } from "react";

import { useTranslation } from "../../i18n/language-context";

const PawIcon = ({ className = "h-3.5 w-3.5" }: { className?: string }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="currentColor">
    <path d="M8.4 9.9c1.1 0 1.9-1.3 1.9-2.9S9.5 4.1 8.4 4.1 6.5 5.4 6.5 7s.8 2.9 1.9 2.9Zm7.2 0c1.1 0 1.9-1.3 1.9-2.9s-.8-2.9-1.9-2.9-1.9 1.3-1.9 2.9.8 2.9 1.9 2.9ZM5.4 13.2c.9-.3 1.2-1.8.7-3.2-.5-1.5-1.7-2.4-2.6-2.1-.9.3-1.2 1.8-.7 3.2.5 1.5 1.7 2.4 2.6 2.1Zm13.2 0c.9.3 2.1-.6 2.6-2.1.5-1.4.2-2.9-.7-3.2-.9-.3-2.1.6-2.6 2.1-.5 1.4-.2 2.9.7 3.2ZM12 11.3c-3.2 0-5.8 2.4-5.8 5.2 0 1.8 1.5 3.1 3.2 3.1 1 0 1.7-.4 2.6-.4s1.6.4 2.6.4c1.7 0 3.2-1.3 3.2-3.1 0-2.8-2.6-5.2-5.8-5.2Z" />
  </svg>
);

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
  errorMessage?: string;
}

const PetImageUploader = ({
  previewUrl,
  isDetailMode,
  fileInputRef,
  onImageChange,
  errorMessage,
}: PetImageUploaderProps) => {
  const { t } = useTranslation();

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-extrabold text-slate-900">{t("pet.photoTitle")}</h2>
      <button
        type="button"
        onClick={() => {
          if (!isDetailMode) {
            fileInputRef.current?.click();
          }
        }}
        className={`relative mt-5 flex h-72 w-full flex-col items-center justify-center overflow-hidden rounded-2xl border border-dashed border-teal-200 bg-gradient-to-b from-teal-50 to-white text-center transition ${
          isDetailMode
            ? "cursor-default"
            : "hover:border-teal-300 hover:bg-teal-50"
        }`}
      >
        {previewUrl ? (
          <img
            src={previewUrl}
            alt={t("pet.photoPreviewAlt")}
            className="h-full w-full object-contain"
          />
        ) : (
          <>
            <span className="absolute left-6 top-6 text-4xl text-teal-100">
              ♡
            </span>
            <span className="absolute bottom-7 right-7 text-4xl text-teal-100">
              <PawIcon className="h-9 w-9" />
            </span>
            <span className="flex h-20 w-20 items-center justify-center rounded-full bg-teal-100 text-teal-700">
              <CameraIcon />
            </span>
            <span className="mt-6 text-base font-extrabold text-slate-800">
              {t("pet.photoUpload")}
            </span>
            <span className="mt-2 text-sm font-semibold text-slate-500">
              {t("pet.photoHint")}
            </span>
          </>
        )}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png"
        onChange={onImageChange}
        disabled={isDetailMode}
        className="hidden"
      />
      {errorMessage ? (
        <p className="mt-1 text-[10px] font-semibold text-red-500">{errorMessage}</p>
      ) : null}
    </section>
  );
};

export default PetImageUploader;
