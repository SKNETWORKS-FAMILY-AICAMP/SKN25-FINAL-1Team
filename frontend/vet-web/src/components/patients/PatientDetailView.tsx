import React, { useState } from "react";
import { ArrowLeft, Settings, X } from "lucide-react";
import { updatePatient } from "../../api/patientApi";
import type { PatientUpdatePayload } from "../../api/patientApi";
import type {
  EmrHistoryRecord,
  PatientProfile,
} from "../../types/patient";
import { editableSpeciesOptions, speciesOptions } from "../../utils/patientUtils";
import { EmptyState } from "../common/EmptyState";

interface PatientDetailViewProps {
  accessToken: string;
  patient: PatientProfile;
  history: EmrHistoryRecord[];
  onBack: () => void;
  onSaved: (updated: PatientProfile) => void;
}

export function PatientDetailView({
  accessToken,
  patient,
  history,
  onBack,
  onSaved,
}: PatientDetailViewProps) {
  const [localPatient, setLocalPatient] = useState(patient);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(patient);
  const [isSaving, setIsSaving] = useState(false);

  const openEdit = () => {
    setDraft({
      ...localPatient,
      weight: normalizeWeightInput(localPatient.weight),
    });
    setIsEditing(true);
  };

  const saveEdit = async () => {
    const normalizedWeight = normalizeWeightInput(draft.weight);
    const parsedWeight = parseFloat(normalizedWeight);
    const displayPatient: PatientProfile = {
      ...draft,
      weight: Number.isFinite(parsedWeight) ? `${normalizedWeight}kg` : "-",
    };
    const payload: PatientUpdatePayload = {
      petname: draft.petName,
      species: draft.species,
      breed: draft.breed,
      gender:
        draft.gender === "수컷"
          ? "male"
          : draft.gender === "암컷"
            ? "female"
            : undefined,
      is_neutered: draft.isNeutered,
      birth_date:
        draft.birthDate && draft.birthDate !== "-"
          ? draft.birthDate.replace(/\./g, "-")
          : undefined,
      weight_kg: Number.isFinite(parsedWeight) ? parsedWeight : undefined,
      notes: draft.notes,
    };

    setIsSaving(true);
    try {
      await updatePatient({
        accessToken,
        petid: localPatient.id,
        payload,
      });

      setLocalPatient(displayPatient);
      onSaved(displayPatient);
      setIsEditing(false);
    } catch (error) {
      console.error("환자 수정 실패:", error);
      alert("환자 정보 수정에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  const updateDraft = (field: keyof PatientProfile, value: string | boolean) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="flex min-h-[calc(100vh-160px)] min-w-0 flex-col">
      {isEditing && (
        <EditPatientModal
          draft={draft}
          isSaving={isSaving}
          onChange={updateDraft}
          onSave={saveEdit}
          onCancel={() => setIsEditing(false)}
        />
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex h-10 items-center gap-2 rounded-lg border border-[#dfe6f1] bg-white px-4 text-sm font-extrabold text-[#344055] transition hover:border-[#8bbcff] hover:text-[#2563eb]"
        >
          <ArrowLeft className="h-4 w-4" />
          환자 관리로 돌아가기
        </button>
        <button
          type="button"
          onClick={openEdit}
          className="flex h-10 items-center gap-2 rounded-lg border border-[#a8cbff] bg-white px-4 text-sm font-extrabold text-[#2563eb] transition hover:bg-[#edf5ff]"
        >
          <Settings className="h-4 w-4" />
          수정
        </button>
      </div>

      <h1 className="mb-4 text-2xl font-extrabold text-[#151b28]">
        {localPatient.petName} <span className="text-[#40506d]">({localPatient.breed})</span>
      </h1>

      <section className="grid min-w-0 grid-cols-1 gap-5 rounded-lg border border-[#e5eaf2] bg-white p-5 shadow-sm xl:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)] xl:p-6 2xl:grid-cols-[180px_minmax(0,1fr)_minmax(0,1fr)]">
        <img
          src={localPatient.imageUrl}
          alt={`${localPatient.petName} 프로필`}
          className="h-36 w-36 rounded-lg object-cover xl:h-40 xl:w-40"
        />

        <InfoGrid
          rows={[
            ["보호자 이름", localPatient.guardianName],
            ["전화번호", localPatient.phone],
          ]}
        />

        <InfoGrid
          rows={[
            ["종류", localPatient.species],
            ["품종", localPatient.breed],
            ["성별", localPatient.gender],
            ["중성화", localPatient.isNeutered ? "O" : "X"],
            ["생년월일", `${localPatient.birthDate} (${localPatient.age})`],
            ["체중", localPatient.weight],
            ["특이사항", localPatient.notes],
          ]}
        />
      </section>

      <section className="mt-4 min-w-0 flex-1 rounded-lg border border-[#e5eaf2] bg-white shadow-sm">
        <div className="border-b border-[#e5eaf2] px-6 py-4">
          <h2 className="text-lg font-extrabold text-[#151b28]">EMR 진료 기록</h2>
        </div>
        {history.length === 0 ? (
          <EmptyState text="등록된 진료 기록이 없습니다." />
        ) : (
          <div className="divide-y divide-[#edf1f6]">
            {history
              .slice()
              .sort((left, right) => right.date.localeCompare(left.date))
              .map((record) => (
                <EmrHistoryRow key={record.id} record={record} />
              ))}
          </div>
        )}
      </section>
    </div>
  );
}

function InfoGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <dl className="grid min-w-0 grid-cols-[96px_minmax(0,1fr)] gap-x-3 gap-y-3 text-sm xl:grid-cols-[112px_minmax(0,1fr)] 2xl:grid-cols-[120px_minmax(0,1fr)]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="font-extrabold text-[#52607a]">{label}</dt>
          <dd className="min-w-0 break-words font-bold leading-6 text-[#1d2a57]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function EmrHistoryRow({ record }: { record: EmrHistoryRecord }) {
  const typeMeta =
    record.type === "treatment"
      ? { label: "진료", className: "bg-[#edf4ff] text-[#4b76c8]" }
      : { label: "예방", className: "bg-[#edf8f1] text-[#4b9a66]" };

  const soapRows = [
    ["S", "주관적", record.soap.subjective],
    ["O", "객관적", record.soap.objective],
    ["A", "평가", record.soap.assessment],
    ["P", "계획", record.soap.plan],
  ].filter(([, , value]) => Boolean(value));
  const onlyMemo =
    soapRows.length === 1 &&
    soapRows[0][0] === "S" &&
    !record.soap.objective &&
    !record.soap.assessment &&
    !record.soap.plan;

  return (
    <article className="grid min-w-0 grid-cols-1 gap-5 px-4 py-5 xl:grid-cols-[140px_minmax(0,1fr)] xl:px-5 2xl:grid-cols-[150px_minmax(0,1fr)_minmax(0,0.9fr)] 2xl:gap-6 2xl:px-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-extrabold tabular-nums text-[#1d2a57]">
            {record.date}
          </p>
          <span className={`rounded-md px-2.5 py-1 text-xs font-extrabold ${typeMeta.className}`}>
            {typeMeta.label}
          </span>
        </div>
        <p className="mt-3 text-sm font-bold text-[#52607a]">{record.doctorName}</p>
      </div>

      <div>
        <p className="text-xs font-extrabold text-[#7a8599]">의사 소견</p>
        <h3 className="mt-1 text-lg font-extrabold text-[#151b28]">{record.title}</h3>
        {onlyMemo ? (
          <p className="mt-3 whitespace-pre-line break-words text-sm font-bold leading-6 text-[#344055]">
            {record.soap.subjective}
          </p>
        ) : (
          <dl className="mt-3 space-y-2 text-sm">
            {soapRows.map(([key, label, value]) => (
              <div key={key} className="grid min-w-0 grid-cols-[22px_54px_minmax(0,1fr)] gap-2 xl:grid-cols-[26px_58px_minmax(0,1fr)]">
                <dt className="font-extrabold text-[#1d2a57]">{key}</dt>
                <dd className="font-extrabold text-[#52607a]">({label})</dd>
                <dd className="min-w-0 whitespace-pre-line break-words font-bold leading-6 text-[#344055]">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <div className="min-w-0 border-t border-[#edf1f6] pt-5 xl:col-start-2 xl:border-l-0 xl:border-t xl:pl-0 2xl:col-start-auto 2xl:border-l 2xl:border-t-0 2xl:pl-6 2xl:pt-0">
        <p className="text-xs font-extrabold text-[#7a8599]">
          {record.type === "prevention" ? "처방/처치" : "처방 내역"}
        </p>
        {record.prescriptions.length === 0 ? (
          <p className="mt-4 text-sm font-bold text-[#7a8599]">처방 내역 없음</p>
        ) : (
          <ol className="mt-4 space-y-3">
            {record.prescriptions.map((line, index) => (
              <li
                key={`${record.id}-${line.name}`}
                className="grid min-w-0 grid-cols-[24px_minmax(0,1fr)_minmax(58px,72px)_minmax(48px,60px)] gap-2 text-sm font-bold text-[#344055] xl:gap-3"
              >
                <span>{index + 1}.</span>
                <span className="min-w-0 break-words">{line.name}</span>
                <span className="min-w-0 break-words text-[#1d2a57]">{line.method}</span>
                <span className="min-w-0 break-words">{line.duration}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </article>
  );
}

function FormField({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="mb-1.5 block text-xs font-extrabold text-[#52607a]">{label}</label>
      {children}
    </div>
  );
}

const inputCls =
  "h-10 w-full rounded-lg border border-[#dfe6f1] bg-white px-3 text-sm font-bold text-[#1d2a57] outline-none transition focus:border-[#8bbcff] focus:ring-2 focus:ring-[#e6f1ff]";
const selectCls =
  "h-10 w-full rounded-lg border border-[#dfe6f1] bg-white px-3 text-sm font-bold text-[#1d2a57] outline-none transition focus:border-[#8bbcff] focus:ring-2 focus:ring-[#e6f1ff]";
const textareaCls =
  "w-full rounded-lg border border-[#dfe6f1] bg-white px-3 py-2 text-sm font-bold text-[#1d2a57] outline-none transition focus:border-[#8bbcff] focus:ring-2 focus:ring-[#e6f1ff] resize-none";

function normalizeWeightInput(value: string) {
  const withoutUnit = value.replace(/kg/gi, "");
  const numeric = withoutUnit.replace(/[^\d.]/g, "");
  const [integerPart, ...decimalParts] = numeric.split(".");
  const decimalPart = decimalParts.join("");

  return decimalParts.length > 0 ? `${integerPart}.${decimalPart}` : integerPart;
}

function EditPatientModal({
  draft,
  isSaving,
  onChange,
  onSave,
  onCancel,
}: {
  draft: PatientProfile;
  isSaving: boolean;
  onChange: (field: keyof PatientProfile, value: string | boolean) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const selectedSpeciesValue = speciesOptions.includes(draft.species)
    ? draft.species
    : "기타";
  const customSpeciesValue = selectedSpeciesValue === "기타" ? draft.species : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[88vh] w-full max-w-[680px] flex-col rounded-2xl bg-white shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-[#e5eaf2] px-6 py-4">
          <h2 className="text-lg font-extrabold text-[#151b28]">환자 정보 수정</h2>
          <button
            type="button"
            onClick={onCancel}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#8595ae] transition hover:bg-[#f0f4fa] hover:text-[#344055]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          <section>
            <p className="mb-4 text-xs font-extrabold uppercase tracking-widest text-[#8595ae]">
              반려동물 정보
            </p>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="이름">
                <input
                  className={inputCls}
                  value={draft.petName}
                  onChange={(e) => onChange("petName", e.target.value)}
                />
              </FormField>
              <FormField label="품종">
                <input
                  className={inputCls}
                  value={draft.breed}
                  onChange={(e) => onChange("breed", e.target.value)}
                />
              </FormField>
              <FormField label="종류">
                <select
                  className={selectCls}
                  value={selectedSpeciesValue}
                  onChange={(e) => {
                    const nextValue = e.target.value;
                    onChange("species", nextValue === "기타" ? "" : nextValue);
                  }}
                >
                  {editableSpeciesOptions.map((species) => (
                    <option key={species} value={species}>
                      {species}
                    </option>
                  ))}
                </select>
              </FormField>
              {selectedSpeciesValue === "기타" && (
                <FormField label="기타 종류 입력">
                  <input
                    className={inputCls}
                    value={customSpeciesValue}
                    onChange={(e) => onChange("species", e.target.value)}
                    placeholder="예: 토끼, 햄스터"
                  />
                </FormField>
              )}
              <FormField label="성별">
                <select
                  className={selectCls}
                  value={draft.gender}
                  onChange={(e) => onChange("gender", e.target.value)}
                >
                  <option value="수컷">수컷</option>
                  <option value="암컷">암컷</option>
                  <option value="-">미확인</option>
                </select>
              </FormField>
              <FormField label="중성화">
                <select
                  className={selectCls}
                  value={draft.isNeutered ? "true" : "false"}
                  onChange={(e) => onChange("isNeutered", e.target.value === "true")}
                >
                  <option value="true">O</option>
                  <option value="false">X</option>
                </select>
              </FormField>
              <FormField label="생년월일">
                <input
                  className={inputCls}
                  value={draft.birthDate}
                  onChange={(e) => onChange("birthDate", e.target.value)}
                />
              </FormField>
              <FormField label="체중">
                <div className="flex items-center gap-2">
                  <input
                    className={inputCls}
                    inputMode="decimal"
                    value={draft.weight}
                    onChange={(e) =>
                      onChange("weight", normalizeWeightInput(e.target.value))
                    }
                  />
                  <span className="shrink-0 text-sm font-extrabold text-[#52607a]">
                    kg
                  </span>
                </div>
              </FormField>
            </div>
            <FormField label="특이사항" className="mt-4">
              <textarea
                className={textareaCls}
                rows={2}
                value={draft.notes}
                onChange={(e) => onChange("notes", e.target.value)}
              />
            </FormField>
          </section>

          <div className="rounded-lg border border-[#ffe4a0] bg-[#fff8ec] px-4 py-3 text-xs font-bold text-[#a06a00]">
            EMR 진료 기록은 수정할 수 없습니다.
          </div>
        </div>

        <div className="flex shrink-0 justify-end gap-3 border-t border-[#e5eaf2] px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="h-10 rounded-lg border border-[#dfe6f1] px-5 text-sm font-extrabold text-[#52607a] transition hover:bg-[#f0f4fa] disabled:cursor-not-allowed disabled:opacity-60"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={isSaving}
            className="h-10 rounded-lg bg-[#2563eb] px-5 text-sm font-extrabold text-white transition hover:bg-[#1a6de8] disabled:cursor-wait disabled:opacity-60"
          >
            {isSaving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
