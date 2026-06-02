import { X } from "lucide-react";
import { useState } from "react";
import { apiClient } from "../../api/client";
import { useAuthStore } from "../../stores/auth-store";
import type { AuthState } from "../../stores/auth-store";
import type { PetInfo } from "../../types/emr";

export function ProfileEditModal({
  patient,
  onClose,
  onSaved,
}: {
  patient: PetInfo;
  onClose: () => void;
  onSaved?: (updated: Partial<PetInfo>) => void;
}) {
  const accessToken = useAuthStore((s: AuthState) => s.session?.accessToken ?? "");
  const [weight, setWeight] = useState(normalizeWeightInput(String(patient.weight_kg)));
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
        },
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      onSaved?.({ weight_kg: parseFloat(weight) || patient.weight_kg, notes });
      onClose();
    } catch (err) {
      console.error("[ProfileEdit] save failed:", err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#111827]/40 px-4">
      <div className="w-full max-w-[520px] rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-[#edf1f6] px-5 py-4">
          <h2 className="text-lg font-extrabold text-[#151b28]">
            환자 정보 수정
          </h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            <X className="h-5 w-5 text-[#59657a]" />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3 px-5 py-5">
          <ProfileInput label="이름" value={patient.pet_name} readOnly />
          <ProfileInput label="종류" value={patient.species} readOnly />
          <ProfileInput label="성별" value={patient.gender} readOnly />
          <label>
            <span className="mb-2 block text-sm font-extrabold text-[#4d5874]">
              체중
            </span>
            <div className="flex items-center gap-2">
              <input
                value={weight}
                inputMode="decimal"
                onChange={(e) => setWeight(normalizeWeightInput(e.target.value))}
                className="h-10 w-full rounded-lg border border-[#dfe6f1] px-3 text-sm font-bold text-[#20283a] outline-none focus:border-[#4a89ff]"
              />
              <span className="shrink-0 text-sm font-extrabold text-[#4d5874]">
                kg
              </span>
            </div>
          </label>
          <ProfileInput label="나이" value={`${patient.age}살`} readOnly />
          <ProfileInput label="생년월일" value={patient.birth_date} readOnly />
          <label className="col-span-2">
            <span className="mb-2 block text-sm font-extrabold text-[#4d5874]">
              특이사항
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="h-24 w-full resize-none rounded-lg border border-[#dfe6f1] px-3 py-2 text-sm font-bold text-[#20283a] outline-none focus:border-[#4a89ff]"
            />
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#edf1f6] px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-[#dfe6f1] px-4 text-sm font-extrabold text-[#59657a]"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="h-10 rounded-lg bg-[#4a89ff] px-4 text-sm font-extrabold text-white disabled:bg-[#c7d1df]"
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
      <span className="mb-2 block text-sm font-extrabold text-[#4d5874]">
        {label}
      </span>
      <input
        defaultValue={value}
        readOnly={readOnly}
        className={`h-10 w-full rounded-lg border border-[#dfe6f1] px-3 text-sm font-bold text-[#20283a] outline-none focus:border-[#4a89ff] ${readOnly ? "bg-[#f7f9fc] text-[#a8b0bf]" : ""}`}
      />
    </label>
  );
}
