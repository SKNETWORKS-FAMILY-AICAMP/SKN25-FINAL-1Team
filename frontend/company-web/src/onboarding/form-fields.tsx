import { ReactNode, useRef, useState } from "react";
import { Plus, Upload, X } from "lucide-react";

import type { UploadedFile } from "./types";

/** 라벨 + 힌트 + 에러를 감싸는 필드 래퍼. */
export function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor?: string;
  required?: boolean;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="block">
      <span className="mb-1.5 flex items-center gap-1 text-sm font-extrabold text-slate-800">
        {label}
        {required ? <span className="text-rose-500">*</span> : null}
      </span>
      {children}
      {hint ? <span className="mt-1 block text-xs font-semibold text-slate-400">{hint}</span> : null}
      {error ? <span className="mt-1 block text-xs font-bold text-rose-500">{error}</span> : null}
    </label>
  );
}

export function SectionCard({
  step,
  title,
  description,
  children,
}: {
  step: number;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-5 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-black text-white">
          {step}
        </span>
        <div>
          <h2 className="text-lg font-black text-slate-900">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-sm font-semibold text-slate-500">{description}</p>
          ) : null}
        </div>
      </div>
      {children}
    </section>
  );
}

/** 글자수 카운터 (max 초과 시 빨강). */
export function CharCount({ value, max }: { value: string; max: number }) {
  const over = value.length > max;
  return (
    <span className={`text-xs font-bold ${over ? "text-rose-500" : "text-slate-400"}`}>
      {value.length}/{max}
    </span>
  );
}

/** 태그 입력 — Enter/콤마로 추가, 개수·글자수 제한. */
export function TagInput({
  value,
  onChange,
  max,
  maxLen,
  placeholder,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  max: number;
  maxLen: number;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const t = draft.trim().slice(0, maxLen);
    if (!t || value.includes(t) || value.length >= max) {
      setDraft("");
      return;
    }
    onChange([...value, t]);
    setDraft("");
  };

  return (
    <div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={value.length >= max ? `최대 ${max}개` : placeholder}
          disabled={value.length >= max}
          className="contact-input"
        />
        <button
          type="button"
          onClick={add}
          disabled={value.length >= max}
          className="mp-btn-secondary shrink-0 px-4"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      {value.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {value.map((tag) => (
            <span key={tag} className="mp-chip gap-1 bg-blue-50 text-blue-700">
              {tag}
              <button
                type="button"
                onClick={() => onChange(value.filter((t) => t !== tag))}
                aria-label={`${tag} 삭제`}
                className="text-blue-400 hover:text-blue-700"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** 파일 업로드 — 이미지는 미리보기(dataURL), 그 외(PDF 등)는 파일명만. */
export function FileField({
  file,
  onChange,
  accept,
  image,
}: {
  file?: UploadedFile;
  onChange: (f: UploadedFile | undefined) => void;
  accept: string;
  /** 이미지 미리보기 표시 여부 */
  image?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handlePick = (f: File) => {
    if (image && f.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = () => onChange({ name: f.name, dataUrl: String(reader.result) });
      reader.readAsDataURL(f);
    } else {
      onChange({ name: f.name });
    }
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handlePick(f);
          e.target.value = "";
        }}
      />
      {file ? (
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          {image && file.dataUrl ? (
            <img src={file.dataUrl} alt={file.name} className="h-14 w-14 rounded-lg object-cover" />
          ) : null}
          <span className="min-w-0 flex-1 truncate text-sm font-bold text-slate-700">{file.name}</span>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="text-xs font-bold text-blue-600 hover:text-blue-700"
          >
            변경
          </button>
          <button
            type="button"
            onClick={() => onChange(undefined)}
            aria-label="파일 삭제"
            className="text-slate-400 hover:text-rose-500"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 py-4 text-sm font-bold text-slate-500 transition hover:border-blue-300 hover:text-blue-600"
        >
          <Upload className="h-4 w-4" />
          파일 선택
        </button>
      )}
    </div>
  );
}
