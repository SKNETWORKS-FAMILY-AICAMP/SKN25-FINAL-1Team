import { X } from "lucide-react";
import { useState } from "react";
import { apiClient } from "../../api/client";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";
import { useAuthStore } from "../../stores/auth-store";
import type { AuthState } from "../../stores/auth-store";
import type { PetInfo } from "../../types/emr";
import { logger } from "@shared/utils/logger";

const GENDER_OPTIONS = [
  { label: "수컷", value: "male" },
  { label: "암컷", value: "female" },
  { label: "미상", value: "unknown" },
] as const;

function toApiGender(display: string): string {
  if (display === "암컷") return "female";
  if (display === "수컷") return "male";
  return "unknown";
}

function toPetInfoGender(api: string): "Female" | "Male" | "unknown" {
  if (api === "female") return "Female";
  if (api === "male") return "Male";
  return "unknown";
}

function toDisplayGender(petInfoGender: string): string {
  if (petInfoGender === "Female") return "암컷";
  if (petInfoGender === "Male") return "수컷";
  return "미상";
}

export function ProfileEditModal({
  patient,
  onClose,
  onSaved,
}: {
  patient: PetInfo;
  onClose: () => void;
  onSaved?: (updated: Partial<PetInfo>) => void;
}) {
  useEscapeToClose(onClose);

  const accessToken = useAuthStore((s: AuthState) => s.session?.accessToken ?? "");
  const [weight, setWeight] = useState(normalizeWeightInput(String(patient.weight_kg)));
  const [gender, setGender] = useState(toDisplayGender(patient.gender));
  const [birthDate, setBirthDate] = useState(patient.birth_date ?? "");
  const [checkupDate, setCheckupDate] = useState(patient.checkup_date ?? "");
  const [notes, setNotes] = useState(patient.notes ?? "");
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await apiClient.patch(
        `/doctor/emr/pet/${patient.pet_id}`,
        {
          weight_kg: parseFloat(weight) || null,
          notes: notes || null,
          // 백엔드 담당자 연동 필요: PetUpdateByDoctor에 아래 필드 추가 후 활성화
          gender: toApiGender(gender),
          birth_date: birthDate || null,
          checkup_date: checkupDate || null,
        },
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      onSaved?.({
        weight_kg: parseFloat(weight) || patient.weight_kg,
        notes,
        gender: toPetInfoGender(toApiGender(gender)),
        birth_date: birthDate,
        checkup_date: checkupDate || undefined,
      });
      onClose();
    } catch (err) {
      logger.error("[ProfileEdit] save failed:", err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4">
      <div className="w-full max-w-[520px] rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-lg font-extrabold text-slate-900">환자 정보 수정</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <X className="h-5 w-5 text-slate-600" />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 px-5 py-5">
          {/* 읽기 전용 */}
          <ProfileInput label="이름" value={patient.pet_name} readOnly />
          <ProfileInput label="종류" value={patient.species} readOnly />

          {/* 성별 드롭다운 */}
          <label>
            <span className="mb-2 block text-sm font-extrabold text-slate-600">성별</span>
            <select
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-500"
            >
              {GENDER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.label}>{opt.label}</option>
              ))}
            </select>
          </label>

          {/* 체중 */}
          <label>
            <span className="mb-2 block text-sm font-extrabold text-slate-600">체중</span>
            <div className="flex items-center gap-2">
              <input
                value={weight}
                inputMode="decimal"
                onChange={(e) => setWeight(normalizeWeightInput(e.target.value))}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-500"
              />
              <span className="shrink-0 text-sm font-extrabold text-slate-600">kg</span>
            </div>
          </label>

          {/* 생년월일 달력 */}
          <label>
            <span className="mb-2 block text-sm font-extrabold text-slate-600">생년월일</span>
            <input
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-500"
            />
          </label>

          {/* 마지막 정기검진일 달력 */}
          <label>
            <span className="mb-2 block text-sm font-extrabold text-slate-600">마지막 정기검진일</span>
            <input
              type="date"
              value={checkupDate}
              onChange={(e) => setCheckupDate(e.target.value)}
              className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-500"
            />
          </label>

          {/* 특이사항 */}
          <label className="col-span-2">
            <span className="mb-2 block text-sm font-extrabold text-slate-600">특이사항</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="h-24 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:border-blue-500"
            />
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-extrabold text-slate-600"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-extrabold text-slate-600 hover:border-blue-500 hover:text-blue-600 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
          >
            {isSaving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}

function normalizeWeightInput(value: string) {
  const withoutUnit = value.replace(/kg/gi, "");
  const numeric = withoutUnit.replace(/[^\d.]/g, "");
  const [integerPart, ...decimalParts] = numeric.split(".");
  const decimalPart = decimalParts.join("");
  return decimalParts.length > 0 ? `${integerPart}.${decimalPart}` : integerPart;
}

function ProfileInput({ label, value, readOnly }: { label: string; value: string; readOnly?: boolean }) {
  return (
    <label>
      <span className="mb-2 block text-sm font-extrabold text-slate-600">{label}</span>
      <input
        defaultValue={value}
        readOnly={readOnly}
        className={`h-10 w-full rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-800 outline-none focus:border-blue-500 ${readOnly ? "bg-slate-50 text-slate-400" : ""}`}
      />
    </label>
  );
}
