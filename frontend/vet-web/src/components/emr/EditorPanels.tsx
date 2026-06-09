import { ChevronDown, FileUp, Search, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { DrugSearchResult } from "../../api/prescriptionApi";
import { searchDrugs } from "../../api/prescriptionApi";
import type { Prescription, UploadedFile } from "../../types/emr";
import { Panel } from "./EmrShared";

export const FORM_OPTIONS = ["PO(경구)", "IV(정맥)", "SC(피하)", "IM(근육)", "외용", "점안", "흡입"];
export const DOSAGE_OPTIONS = [
  "0.5mg/kg", "1mg/kg", "2mg/kg", "5mg/kg", "10mg/kg",
  "0.5ml", "1ml", "2ml", "5ml",
  "1정", "1/2정", "2정",
];
export const FREQUENCY_OPTIONS = ["SID(하루 1회)", "BID(하루 2회)", "TID(하루 3회)", "QID(하루 4회)", "필요 시"];
export const DURATION_OPTIONS = [3, 5, 7, 10, 14, 30];

type PhotoUploadFieldsProps = {
  files: UploadedFile[];
  onUploadFile: (file: File) => void;
  onRemoveFile: (fileId: number) => void;
  onPreviewImage: (url: string, label: string) => void;
  isUploading?: boolean;
  uploadError?: string | null;
  isReadOnly?: boolean;
};

function EditableComboBox({
  value,
  options,
  onChange,
  placeholder = "선택",
  isReadOnly = false,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  placeholder?: string;
  isReadOnly?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [hasTyped, setHasTyped] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const reactId = useId();
  const listboxId = `${reactId}-options`;
  const filteredOptions = hasTyped
    ? options.filter((option) => option.toLowerCase().includes(value.toLowerCase()))
    : options;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setHasTyped(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    setActiveIndex(0);
  }, [value]);

  useEffect(() => {
    if (activeIndex > filteredOptions.length - 1) {
      setActiveIndex(Math.max(filteredOptions.length - 1, 0));
    }
  }, [activeIndex, filteredOptions.length]);

  const selectOption = (option: string) => {
    onChange(option);
    setIsOpen(false);
    setHasTyped(false);
  };

  if (isReadOnly) return <span className="text-xs text-[#4d5874]">{value || "-"}</span>;

  return (
    <div ref={wrapperRef} className="relative">
      <input
        value={value}
        onFocus={() => { setHasTyped(false); setIsOpen(true); }}
        onChange={(event) => {
          setHasTyped(true);
          onChange(event.target.value);
          setIsOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setIsOpen(true);
            if (filteredOptions.length > 0) {
              setActiveIndex((index) => Math.min(index + 1, filteredOptions.length - 1));
            }
          }

          if (event.key === "ArrowUp") {
            event.preventDefault();
            setIsOpen(true);
            if (filteredOptions.length > 0) {
              setActiveIndex((index) => Math.max(index - 1, 0));
            }
          }

          if (event.key === "Enter" && isOpen && filteredOptions[activeIndex]) {
            event.preventDefault();
            selectOption(filteredOptions[activeIndex]);
          }

          if (event.key === "Escape") {
            setIsOpen(false);
            setHasTyped(false);
          }
        }}
        placeholder={placeholder}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-activedescendant={
          isOpen && filteredOptions[activeIndex]
            ? `${listboxId}-${activeIndex}`
            : undefined
        }
        className="h-7 w-full min-w-0 rounded border border-[#dfe6f1] bg-white px-1.5 pr-6 text-xs font-bold outline-none transition placeholder:text-[#697386] focus:border-[#357b70] focus:ring-1 focus:ring-[#eef5f4]"
      />
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="absolute right-1 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center text-[#64748b]"
        aria-label={`${placeholder} 옵션 열기`}
      >
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {isOpen && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+4px)] z-20 max-h-36 overflow-y-auto rounded-md border border-[#dfe6f1] bg-white py-1 shadow-lg"
        >
          {filteredOptions.length > 0 ? (
            filteredOptions.map((option, index) => (
              <button
                type="button"
                key={option}
                id={`${listboxId}-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => selectOption(option)}
                className={[
                  "block w-full truncate px-2 py-1.5 text-left text-xs font-bold",
                  index === activeIndex
                    ? "bg-[#eef5f4] text-[#2f6f67]"
                    : "text-[#4d5874] hover:bg-[#eef5f4] hover:text-[#2f6f67]",
                ].join(" ")}
              >
                {option}
              </button>
            ))
          ) : (
            <div className="px-2 py-1.5 text-xs font-bold text-[#8a94a6]">
              직접 입력 중
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DurationComboBox({
  value,
  onChange,
  isReadOnly = false,
}: {
  value: number;
  onChange: (v: number) => void;
  isReadOnly?: boolean;
}) {
  const durationValue = value ? `${value}일` : "";

  if (isReadOnly) return <span className="text-xs text-[#4d5874]">{value}일</span>;

  return (
    <EditableComboBox
      value={durationValue}
      options={DURATION_OPTIONS.map((duration) => `${duration}일`)}
      onChange={(nextValue) => {
        const parsed = parseInt(nextValue.replace(/[^0-9]/g, ""), 10);
        onChange(Number.isNaN(parsed) ? 0 : parsed);
      }}
      placeholder="기간"
    />
  );
}

export function EditorPanel({
  value,
  onChange,
  onCompleteVisit,
  files,
  onUploadFile,
  onRemoveFile,
  onPreviewImage,
  errorMessage = null,
  isUploading = false,
  uploadError = null,
  isReadOnly = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onCompleteVisit: () => void;
  files: UploadedFile[];
  onUploadFile: (file: File) => void;
  onRemoveFile: (fileId: number) => void;
  onPreviewImage: (url: string, label: string) => void;
  errorMessage?: string | null;
  isUploading?: boolean;
  uploadError?: string | null;
  isReadOnly?: boolean;
}) {
  return (
    <Panel className="flex flex-1 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-[#edf1f6] px-4 py-2">
        <h2 className="text-sm font-extrabold text-[#151b28]">
          현재 진료 내용 입력
        </h2>
        <button
          type="button"
          onClick={onCompleteVisit}
          disabled={isReadOnly}
          className="h-8 rounded-md bg-[#2f6f67] px-3 text-xs font-extrabold text-white transition hover:bg-[#255e57] disabled:cursor-not-allowed disabled:bg-[#c7d1df]"
        >
          진료 완료
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-3">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="진료 내용을 입력하세요..."
          readOnly={isReadOnly}
          className="min-h-[120px] flex-1 w-full resize-none rounded-md border border-[#dfe6f1] px-3 py-2.5 text-xs font-bold leading-5 text-[#20283a] outline-none transition placeholder:text-[#a8b0bf] focus:border-[#357b70] focus:ring-2 focus:ring-[#eef5f4] read-only:bg-[#f9fafb] read-only:text-[#697386] read-only:focus:border-[#dfe6f1] read-only:focus:ring-0"
        />
        {errorMessage && (
          <p className="text-xs font-bold text-red-500">{errorMessage}</p>
        )}
        <div className="border-t border-[#edf1f6] pt-3">
          <h3 className="mb-2 text-sm font-extrabold text-[#151b28]">사진 등록</h3>
          <PhotoUploadFields
            files={files}
            onUploadFile={onUploadFile}
            onRemoveFile={onRemoveFile}
            onPreviewImage={onPreviewImage}
            isUploading={isUploading}
            uploadError={uploadError}
            isReadOnly={isReadOnly}
          />
        </div>
      </div>
    </Panel>
  );
}

function PhotoUploadFields({
  files,
  onUploadFile,
  onRemoveFile,
  onPreviewImage,
  isUploading = false,
  uploadError = null,
  isReadOnly = false,
}: PhotoUploadFieldsProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const disabled = isReadOnly || isUploading;

  const openFilePicker = () => {
    if (!disabled) fileInputRef.current?.click();
  };

  const handleFilesSelected = (fileList: FileList | null) => {
    if (!fileList) return;
    Array.from(fileList).forEach((file) => onUploadFile(file));
  };

  return (
    <div className="space-y-2">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,application/pdf,video/mp4"
        multiple
        className="hidden"
        onChange={(event) => {
          handleFilesSelected(event.target.files);
          // 같은 파일을 다시 선택해도 onChange가 발생하도록 비운다.
          event.target.value = "";
        }}
      />
      <div className="flex flex-wrap gap-2">
        {files.map((file) => (
          <div
            key={file.id}
            className="relative h-16 w-16 overflow-hidden rounded-md bg-[#edf1f6]"
          >
            <button
              type="button"
              onClick={() => onPreviewImage(file.url, file.label)}
              className="block h-full w-full"
            >
              <img
                src={file.url}
                alt={file.label}
                className="h-full w-full object-cover"
              />
            </button>
            <button
              type="button"
              onClick={() => onRemoveFile(file.id)}
              aria-label="첨부 삭제"
              disabled={isReadOnly}
              className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[#111827]/70 text-white disabled:hidden"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={openFilePicker}
        disabled={disabled}
        onDragOver={(event) => {
          if (!disabled) event.preventDefault();
        }}
        onDrop={(event) => {
          if (disabled) return;
          event.preventDefault();
          handleFilesSelected(event.dataTransfer.files);
        }}
        className="grid min-h-12 w-full grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2 gap-y-0.5 rounded-md border border-dashed border-[#cfd8e6] px-3 py-2 text-left text-xs font-extrabold text-[#59657a] transition hover:border-[#357b70] hover:text-[#2f6f67] disabled:cursor-not-allowed disabled:border-[#e5eaf2] disabled:bg-[#f9fafb] disabled:text-[#a8b0bf]"
      >
        <FileUp className="row-span-2 h-4 w-4 shrink-0" />
        <span className="min-w-0 break-keep leading-4">
          {isUploading ? "업로드 중..." : "파일을 드래그하거나 클릭하여 업로드"}
        </span>
        <span className="min-w-0 break-keep text-[11px] font-bold leading-4 text-[#8a94a6]">
          JPG, PNG, PDF, MP4 · 최대 50MB
        </span>
      </button>
      {uploadError && (
        <p className="text-xs font-bold text-red-500">{uploadError}</p>
      )}
    </div>
  );
}

export function PhotoUploadPanel(props: PhotoUploadFieldsProps) {
  return (
    <Panel>
      <div className="border-b border-[#edf1f6] px-4 py-2">
        <h2 className="text-sm font-extrabold text-[#151b28]">사진 등록</h2>
      </div>
      <div className="px-4 py-3">
        <PhotoUploadFields {...props} />
      </div>
    </Panel>
  );
}

export function PrescriptionInputPanel({
  prescriptions,
  onRemove,
  onGenerate,
  onOpenPreview,
  onAdd,
  onUpdate,
  accessToken,
  errorMessage = null,
  previewErrorMessage = null,
  isReadOnly = false,
  isGenerating = false,
}: {
  prescriptions: Prescription[];
  onRemove: (clientId: string) => void;
  onGenerate: () => void;
  onOpenPreview: () => void;
  onAdd?: (drug: DrugSearchResult) => void;
  onUpdate?: (clientId: string, field: keyof Prescription, value: string | number) => void;
  accessToken?: string;
  errorMessage?: string | null;
  previewErrorMessage?: string | null;
  isReadOnly?: boolean;
  isGenerating?: boolean;
}) {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<DrugSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeResultIndex, setActiveResultIndex] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const drugSearchId = useId();
  const drugListboxId = `${drugSearchId}-drug-results`;

  useEffect(() => {
    if (!keyword.trim() || !accessToken) {
      setResults([]);
      setIsOpen(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const drugs = await searchDrugs({ accessToken, keyword });
        setResults(drugs);
        setIsOpen(drugs.length > 0);
      } catch {
        setResults([]);
        setIsOpen(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [keyword, accessToken]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    setActiveResultIndex(0);
  }, [keyword]);

  useEffect(() => {
    if (activeResultIndex > results.length - 1) {
      setActiveResultIndex(Math.max(results.length - 1, 0));
    }
  }, [activeResultIndex, results.length]);

  const handleSelect = (drug: DrugSearchResult) => {
    onAdd?.(drug);
    setKeyword("");
    setResults([]);
    setIsOpen(false);
  };

  return (
    <Panel className="flex flex-1 flex-col">
      <div className="shrink-0 flex items-center justify-between gap-2 border-b border-[#edf1f6] px-3 py-2">
        <h2 className="shrink-0 text-sm font-extrabold text-[#151b28]">처방전</h2>
        <div className="flex min-w-0 items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={onGenerate}
            disabled={isReadOnly || isGenerating}
            className="flex h-9 items-center gap-1.5 rounded-md border border-[#dfe6f1] bg-white px-3.5 text-xs font-extrabold text-[#4d5874] transition hover:border-[#357b70] hover:text-[#2f6f67] disabled:cursor-not-allowed disabled:bg-[#f9fafb] disabled:text-[#a8b0bf]"
          >
            {isGenerating ? (
              <>
                <svg className="h-4 w-4 animate-spin text-[#357b70]" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                생성 중...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 text-[#357b70]" strokeWidth={2.2} />
                처방전 자동 생성
              </>
            )}
          </button>
          <button
            type="button"
            onClick={onOpenPreview}
            className="h-9 rounded-md border border-[#dfe6f1] bg-white px-3.5 text-xs font-extrabold text-[#4d5874] transition hover:border-[#357b70] hover:text-[#2f6f67]"
          >
            미리보기
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto space-y-2 px-3 py-2.5">
        <div ref={wrapperRef} className="relative">
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                if (results.length > 0) {
                  setIsOpen(true);
                  setActiveResultIndex((index) => Math.min(index + 1, results.length - 1));
                }
              }

              if (event.key === "ArrowUp") {
                event.preventDefault();
                if (results.length > 0) {
                  setIsOpen(true);
                  setActiveResultIndex((index) => Math.max(index - 1, 0));
                }
              }

              if (event.key === "Enter" && isOpen && results[activeResultIndex]) {
                event.preventDefault();
                handleSelect(results[activeResultIndex]);
              }

              if (event.key === "Escape") {
                setIsOpen(false);
              }
            }}
            placeholder="약제명 검색 (예: 아모시실린)"
            readOnly={isReadOnly}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={isOpen}
            aria-controls={drugListboxId}
            aria-activedescendant={
              isOpen && results[activeResultIndex]
                ? `${drugListboxId}-${activeResultIndex}`
                : undefined
            }
            className="h-8 w-full rounded-md border border-[#357b70] px-2.5 pr-8 text-xs font-bold outline-none ring-2 ring-[#eef5f4] read-only:border-[#dfe6f1] read-only:bg-[#f9fafb] read-only:text-[#8a94a6] read-only:ring-0"
          />
          <Search className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#357b70]" />
          {isOpen && (
            <ul
              id={drugListboxId}
              role="listbox"
              className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-[#dfe6f1] bg-white shadow-lg"
            >
              {results.map((drug, index) => (
                <li key={drug.drugid} role="presentation">
                  <button
                    type="button"
                    id={`${drugListboxId}-${index}`}
                    role="option"
                    aria-selected={index === activeResultIndex}
                    onMouseEnter={() => setActiveResultIndex(index)}
                    onClick={() => handleSelect(drug)}
                    className={[
                      "w-full px-4 py-2 text-left text-sm",
                      index === activeResultIndex ? "bg-[#eef5f4]" : "hover:bg-[#eef5f4]",
                    ].join(" ")}
                  >
                    <span className="font-extrabold text-[#20283a]">{drug.name}</span>
                    {drug.ingredient_kr && (
                      <span className="ml-2 text-xs text-[#8a94a6]">{drug.ingredient_kr}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="relative overflow-visible rounded-md border border-[#e8edf4]">
          <table className="w-full table-fixed text-left">
            <thead className="bg-[#f8fafb] text-[11px] font-extrabold text-[#697386]">
              <tr>
                <th className="w-[24%] px-2 py-1.5">약제명</th>
                <th className="w-[15%] px-1 py-1.5">형태</th>
                <th className="w-[17%] px-1 py-1.5">용량</th>
                <th className="w-[19%] px-1 py-1.5">용법</th>
                <th className="w-[12%] px-1 py-1.5">기간</th>
                <th
                  className={`w-[7%] px-1 py-1.5 text-center ${!isReadOnly && prescriptions.length > 0 ? "cursor-pointer select-none hover:text-[#2f6f67]" : ""}`}
                  onClick={() => {
                    if (isReadOnly || prescriptions.length === 0) return;
                    const allChecked = prescriptions.every((p) => (p.pil_seon ?? "") === "필");
                    prescriptions.forEach((p, idx) => {
                      const clientId = p.client_id ?? `${p.drug_name}-${idx}`;
                      onUpdate?.(clientId, "pil_seon", allChecked ? "선" : "필");
                    });
                  }}
                  title={!isReadOnly && prescriptions.length > 0 ? "전체 선택/해제" : undefined}
                >
                  필수
                </th>
                <th className="w-[6%] px-1 py-1.5 text-center">삭제</th>
              </tr>
            </thead>
            <tbody>
              {prescriptions.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-3 py-6 text-center text-xs font-bold text-[#8a94a6]"
                  >
                    검색을 통해 약을 추가해주세요.
                  </td>
                </tr>
              ) : (
                prescriptions.map((prescription, index) => {
                  const clientId = prescription.client_id ?? `${prescription.drug_name}-${index}`;
                  const pilSeon = prescription.pil_seon ?? "";
                  return (
                  <tr
                    key={clientId}
                    className="border-t border-[#edf1f6] text-xs font-bold text-[#4d5874]"
                  >
                    <td className="px-2 py-1.5 align-top font-extrabold text-[#20283a]">
                      <span className="block min-w-0 truncate" title={prescription.drug_name}>
                        {prescription.drug_name}
                      </span>
                    </td>
                    <td className="px-1 py-1.5 align-top">
                      <EditableComboBox
                        value={prescription.form}
                        options={FORM_OPTIONS}
                        onChange={(v) => onUpdate?.(clientId, "form", v)}
                        placeholder="형태"
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-1 py-1.5 align-top">
                      <EditableComboBox
                        value={prescription.dosage}
                        options={DOSAGE_OPTIONS}
                        onChange={(v) => onUpdate?.(clientId, "dosage", v)}
                        placeholder="용량"
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-1 py-1.5 align-top">
                      <EditableComboBox
                        value={prescription.frequency}
                        options={FREQUENCY_OPTIONS}
                        onChange={(v) => onUpdate?.(clientId, "frequency", v)}
                        placeholder="용법"
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-1 py-1.5 align-top">
                      <DurationComboBox
                        value={prescription.duration_days}
                        onChange={(v) => onUpdate?.(clientId, "duration_days", v)}
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-1 py-1.5 text-center align-middle">
                      {isReadOnly ? (
                        <span className="text-xs text-[#4d5874]">{pilSeon || "선"}</span>
                      ) : (
                        <input
                          type="checkbox"
                          checked={pilSeon === "필"}
                          onChange={() =>
                            onUpdate?.(clientId, "pil_seon", pilSeon === "필" ? "선" : "필")
                          }
                          aria-label={`${prescription.drug_name} 필수 여부`}
                          className="h-4 w-4 cursor-pointer accent-[#2f6f67]"
                        />
                      )}
                    </td>
                    <td className="px-1 py-1.5 text-center align-middle">
                      <button
                        type="button"
                        onClick={() => onRemove(clientId)}
                        disabled={isReadOnly}
                        aria-label={`${prescription.drug_name} 삭제`}
                        className="inline-flex h-7 w-7 items-center justify-center rounded text-[#ef4444] hover:bg-red-50 disabled:cursor-not-allowed disabled:text-[#c7d1df]"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {errorMessage && (
          <p className="text-xs font-bold text-red-500">{errorMessage}</p>
        )}
        {previewErrorMessage && (
          <p className="text-xs font-bold text-red-500">{previewErrorMessage}</p>
        )}
      </div>
    </Panel>
  );
}
