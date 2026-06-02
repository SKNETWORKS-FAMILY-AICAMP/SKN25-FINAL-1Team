import { AlignLeft, Bold, FileUp, Italic, List, Plus, Search, Trash2, Underline, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DrugSearchResult } from "../../api/prescriptionApi";
import { searchDrugs } from "../../api/prescriptionApi";
import type { Prescription, UploadedFile } from "../../types/emr";
import { Panel } from "./EmrShared";

const FORM_OPTIONS = ["PO(경구)", "IV(정맥)", "SC(피하)", "IM(근육)", "외용", "점안", "흡입"];
const DOSAGE_OPTIONS = [
  "0.5mg/kg", "1mg/kg", "2mg/kg", "5mg/kg", "10mg/kg",
  "0.5ml", "1ml", "2ml", "5ml",
  "1정", "1/2정", "2정",
];
const DURATION_OPTIONS = [3, 5, 7, 10, 14, 30];

function EditableSelect({
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
  const isCustomValue = value !== "" && !options.includes(value);
  const [showInput, setShowInput] = useState(isCustomValue);

  useEffect(() => {
    if (!value) setShowInput(false);
  }, [value]);

  if (isReadOnly) return <span className="text-sm text-[#4d5874]">{value || "-"}</span>;

  if (showInput) {
    return (
      <div className="flex items-center gap-1">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded border border-[#dfe6f1] px-2 py-1 text-sm outline-none focus:border-[#4a89ff]"
          autoFocus
        />
        <button
          type="button"
          onClick={() => { onChange(""); setShowInput(false); }}
          className="shrink-0 text-[#a8b0bf] hover:text-[#ef4444]"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => {
        if (e.target.value === "__custom__") {
          setShowInput(true);
          onChange("");
        } else {
          onChange(e.target.value);
        }
      }}
      className="w-full rounded border border-[#dfe6f1] bg-white px-2 py-1 text-sm outline-none focus:border-[#4a89ff]"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
      <option value="__custom__">직접 입력...</option>
    </select>
  );
}

function DurationSelect({
  value,
  onChange,
  isReadOnly = false,
}: {
  value: number;
  onChange: (v: number) => void;
  isReadOnly?: boolean;
}) {
  const isCustomValue = value !== 0 && !DURATION_OPTIONS.includes(value);
  const [showInput, setShowInput] = useState(isCustomValue);

  useEffect(() => {
    if (!value) setShowInput(false);
  }, [value]);

  if (isReadOnly) return <span className="text-sm text-[#4d5874]">{value}일</span>;

  if (showInput) {
    return (
      <div className="flex items-center gap-1">
        <input
          type="number"
          min={1}
          value={value || ""}
          onChange={(e) => onChange(parseInt(e.target.value, 10) || 0)}
          className="w-14 rounded border border-[#dfe6f1] px-2 py-1 text-sm outline-none focus:border-[#4a89ff]"
          autoFocus
        />
        <span className="shrink-0 text-sm text-[#697386]">일</span>
        <button
          type="button"
          onClick={() => { onChange(0); setShowInput(false); }}
          className="shrink-0 text-[#a8b0bf] hover:text-[#ef4444]"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => {
        if (e.target.value === "__custom__") {
          setShowInput(true);
          onChange(0);
        } else {
          onChange(parseInt(e.target.value, 10));
        }
      }}
      className="w-full rounded border border-[#dfe6f1] bg-white px-2 py-1 text-sm outline-none focus:border-[#4a89ff]"
    >
      <option value={0}>기간 선택</option>
      {DURATION_OPTIONS.map((d) => (
        <option key={d} value={d}>{d}일</option>
      ))}
      <option value="__custom__">직접 입력...</option>
    </select>
  );
}

export function EditorPanel({
  value,
  count,
  onChange,
  onCompleteVisit,
  isReadOnly = false,
}: {
  value: string;
  count: number;
  onChange: (value: string) => void;
  onCompleteVisit: () => void;
  isReadOnly?: boolean;
}) {
  return (
    <Panel>
      <div className="flex items-center justify-between border-b border-[#edf1f6] px-5 py-3">
        <h2 className="text-base font-extrabold text-[#151b28]">
          현재 진료 내용 입력
        </h2>
        <button
          type="button"
          onClick={onCompleteVisit}
          disabled={isReadOnly}
          className="h-9 rounded-lg bg-[#16a34a] px-4 text-sm font-extrabold text-white transition hover:bg-[#13863f] disabled:cursor-not-allowed disabled:bg-[#c7d1df]"
        >
          진료 완료
        </button>
      </div>
      <div className="flex items-center gap-2 border-b border-[#edf1f6] px-5 py-2 text-[#4d5874]">
        <select
          disabled={isReadOnly}
          className="h-8 rounded-md border border-[#dfe6f1] px-2 text-xs font-bold outline-none disabled:bg-[#f5f7fa] disabled:text-[#a8b0bf]"
        >
          <option>Pretendard</option>
        </select>
        <select
          disabled={isReadOnly}
          className="h-8 rounded-md border border-[#dfe6f1] px-2 text-xs font-bold outline-none disabled:bg-[#f5f7fa] disabled:text-[#a8b0bf]"
        >
          <option>14</option>
        </select>
        {[Bold, Italic, Underline, AlignLeft, List].map((Icon) => (
          <button
            key={Icon.displayName}
            type="button"
            disabled={isReadOnly}
            className="flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#edf5ff] hover:text-[#2563eb] disabled:cursor-not-allowed disabled:text-[#a8b0bf]"
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}
      </div>
      <div className="px-5 py-4">
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="진료 내용을 입력하세요..."
          readOnly={isReadOnly}
          className="h-36 w-full resize-none rounded-lg border border-[#dfe6f1] px-4 py-3 text-sm font-bold leading-6 text-[#20283a] outline-none transition placeholder:text-[#a8b0bf] focus:border-[#4a89ff] focus:ring-4 focus:ring-[#edf5ff] read-only:bg-[#f8fafc] read-only:text-[#697386] read-only:focus:border-[#dfe6f1] read-only:focus:ring-0"
        />
        <p className="mt-2 text-right text-xs font-extrabold text-[#8a94a6]">
          글자 수: {count}
        </p>
      </div>
    </Panel>
  );
}

export function PhotoUploadPanel({
  files,
  onUploadFile,
  onRemoveFile,
  onPreviewImage,
  isUploading = false,
  uploadError = null,
  isReadOnly = false,
}: {
  files: UploadedFile[];
  onUploadFile: (file: File) => void;
  onRemoveFile: (fileId: number) => void;
  onPreviewImage: (url: string, label: string) => void;
  isUploading?: boolean;
  uploadError?: string | null;
  isReadOnly?: boolean;
}) {
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
    <Panel>
      <div className="border-b border-[#edf1f6] px-5 py-3">
        <h2 className="text-base font-extrabold text-[#151b28]">사진 등록</h2>
      </div>
      <div className="space-y-3 px-5 py-4">
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
        <div className="flex flex-wrap gap-3">
          {files.map((file) => (
            <button
              type="button"
              key={file.id}
              onClick={() => onPreviewImage(file.url, file.label)}
              className="relative h-20 w-20 overflow-hidden rounded-lg bg-[#edf1f6]"
            >
              <img
                src={file.url}
                alt={file.label}
                className="h-full w-full object-cover"
              />
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onRemoveFile(file.id);
                }}
                aria-label="첨부 삭제"
                disabled={isReadOnly}
                className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[#111827]/70 text-white disabled:hidden"
              >
                <X className="h-3 w-3" />
              </button>
            </button>
          ))}
          <button
            type="button"
            onClick={openFilePicker}
            disabled={disabled}
            className="flex h-20 w-20 flex-col items-center justify-center rounded-lg border border-dashed border-[#cfd8e6] text-sm font-extrabold text-[#4d5874] transition hover:border-[#4a89ff] hover:text-[#2563eb] disabled:cursor-not-allowed disabled:border-[#e5eaf2] disabled:bg-[#f8fafc] disabled:text-[#a8b0bf]"
          >
            <Plus className="h-6 w-6" />
            추가
          </button>
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
          className="flex h-16 w-full items-center justify-center gap-3 rounded-lg border border-dashed border-[#cfd8e6] text-sm font-extrabold text-[#59657a] transition hover:border-[#4a89ff] hover:text-[#2563eb] disabled:cursor-not-allowed disabled:border-[#e5eaf2] disabled:bg-[#f8fafc] disabled:text-[#a8b0bf]"
        >
          <FileUp className="h-5 w-5" />
          {isUploading ? "업로드 중..." : "파일을 드래그하거나 클릭하여 업로드"}
          <span className="text-xs font-bold text-[#8a94a6]">
            JPG, PNG, PDF, MP4 · 최대 50MB
          </span>
        </button>
        {uploadError && (
          <p className="text-xs font-bold text-red-500">{uploadError}</p>
        )}
      </div>
    </Panel>
  );
}

export function PrescriptionInputPanel({
  prescriptions,
  onRemove,
  onGenerate,
  onAdd,
  onUpdate,
  onSave,
  accessToken,
  isReadOnly = false,
}: {
  prescriptions: Prescription[];
  onRemove: (name: string) => void;
  onGenerate: () => void;
  onAdd?: (drug: DrugSearchResult) => void;
  onUpdate?: (drug_name: string, field: keyof Prescription, value: string | number) => void;
  onSave?: () => void;
  accessToken?: string;
  isReadOnly?: boolean;
}) {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<DrugSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

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

  const handleSelect = (drug: DrugSearchResult) => {
    onAdd?.(drug);
    setKeyword("");
    setResults([]);
    setIsOpen(false);
  };

  return (
    <Panel>
      <div className="border-b border-[#edf1f6] px-5 py-3">
        <h2 className="text-base font-extrabold text-[#151b28]">처방전</h2>
      </div>
      <div className="space-y-3 px-5 py-4">
        <div ref={wrapperRef} className="relative">
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="약제명 검색 (예: 아모시실린)"
            readOnly={isReadOnly}
            className="h-10 w-full rounded-lg border border-[#4a89ff] px-4 pr-10 text-sm font-bold outline-none ring-4 ring-[#edf5ff] read-only:border-[#dfe6f1] read-only:bg-[#f8fafc] read-only:text-[#8a94a6] read-only:ring-0"
          />
          <Search className="absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-[#4a89ff]" />
          {isOpen && (
            <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-[#dfe6f1] bg-white shadow-lg">
              {results.map((drug) => (
                <li key={drug.drugid}>
                  <button
                    type="button"
                    onClick={() => handleSelect(drug)}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-[#edf5ff]"
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

        <div className="overflow-hidden rounded-lg border border-[#e8edf4]">
          <table className="w-full table-fixed text-left">
            <thead className="bg-[#f7f9fc] text-xs font-extrabold text-[#697386]">
              <tr>
                <th className="w-[28%] px-4 py-3">약제명</th>
                <th className="w-[20%] px-3 py-3">형태</th>
                <th className="w-[20%] px-3 py-3">용량</th>
                <th className="w-[20%] px-3 py-3">기간</th>
                <th className="w-[12%] px-3 py-3">삭제</th>
              </tr>
            </thead>
            <tbody>
              {prescriptions.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-9 text-center text-sm font-bold text-[#8a94a6]"
                  >
                    검색을 통해 약을 추가해주세요.
                  </td>
                </tr>
              ) : (
                prescriptions.map((prescription) => (
                  <tr
                    key={prescription.drug_name}
                    className="border-t border-[#edf1f6] text-sm font-bold text-[#4d5874]"
                  >
                    <td className="px-4 py-2 font-extrabold text-[#20283a]">
                      {prescription.drug_name}
                    </td>
                    <td className="px-2 py-2">
                      <EditableSelect
                        value={prescription.form}
                        options={FORM_OPTIONS}
                        onChange={(v) => onUpdate?.(prescription.drug_name, "form", v)}
                        placeholder="형태"
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <EditableSelect
                        value={prescription.dosage}
                        options={DOSAGE_OPTIONS}
                        onChange={(v) => onUpdate?.(prescription.drug_name, "dosage", v)}
                        placeholder="용량"
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <DurationSelect
                        value={prescription.duration_days}
                        onChange={(v) => onUpdate?.(prescription.drug_name, "duration_days", v)}
                        isReadOnly={isReadOnly}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => onRemove(prescription.drug_name)}
                        disabled={isReadOnly}
                        className="text-[#ef4444] disabled:cursor-not-allowed disabled:text-[#c7d1df]"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onSave}
            disabled={isReadOnly}
            className="h-10 rounded-lg border border-[#dfe6f1] px-5 text-sm font-extrabold text-[#4d5874] disabled:cursor-not-allowed disabled:bg-[#f8fafc] disabled:text-[#a8b0bf]"
          >
            저장
          </button>
          <button
            type="button"
            onClick={onGenerate}
            disabled={isReadOnly}
            className="h-10 rounded-lg bg-[#4a89ff] px-5 text-sm font-extrabold text-white transition hover:bg-[#2563eb] disabled:cursor-not-allowed disabled:bg-[#c7d1df]"
          >
            처방전 자동 생성
          </button>
        </div>
      </div>
    </Panel>
  );
}
