import { Edit3 } from "lucide-react";
import type { EmrResult, PetInfo, Prescription } from "../../types/emr";
import { Panel } from "./EmrShared";

// 프로필 이미지가 없거나 깨졌을 때 보여줄 기본 플레이스홀더(연한 회색 배경 + 발바닥).
const PROFILE_IMAGE_FALLBACK =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"><rect width="96" height="96" rx="8" fill="#eef2f8"/><g fill="#b9c4d6"><ellipse cx="36" cy="40" rx="6" ry="8"/><ellipse cx="60" cy="40" rx="6" ry="8"/><ellipse cx="26" cy="54" rx="5" ry="7"/><ellipse cx="70" cy="54" rx="5" ry="7"/><path d="M48 52c-9 0-16 7-16 14 0 5 4 8 9 8 3 0 5-1 7-1s4 1 7 1c5 0 9-3 9-8 0-7-7-14-16-14z"/></g></svg>`
  );

export function PatientInfoPanel({
  patient,
  onEdit,
  isReadOnly = false,
}: {
  patient: PetInfo;
  onEdit: () => void;
  isReadOnly?: boolean;
}) {
  return (
    <Panel>
      <div className="flex items-start justify-between px-5 py-4">
        <div className="flex gap-4">
          <img
            src={patient.profile_image || PROFILE_IMAGE_FALLBACK}
            alt={`${patient.pet_name} 사진`}
            className="h-24 w-24 rounded-lg object-cover"
            onError={(event) => {
              const img = event.currentTarget;
              if (img.src !== PROFILE_IMAGE_FALLBACK) {
                img.src = PROFILE_IMAGE_FALLBACK;
              }
            }}
          />
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-extrabold text-[#151b28]">
                {patient.pet_name}
              </h1>
              <span className="text-2xl font-extrabold text-[#f43f7c]">
                {patient.gender === "Female" ? "♀" : "♂"}
              </span>
            </div>
            <p className="mt-2 text-sm font-extrabold text-[#4d5874]">
              {patient.species} | {patient.gender} | {patient.weight_kg}kg |{" "}
              {patient.age}살({patient.birth_date})
            </p>
            <p className="mt-3 text-sm font-extrabold text-[#4d5874]">
              최근 내원일: {patient.last_visit}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <InfoTag label={patient.is_neutered ? "중성화 O" : "중성화 X"} />
              <InfoTag label={patient.notes} />
            </div>
            <a
              href="#patient-profile"
              className="mt-3 inline-block text-sm font-extrabold text-[#2563eb]"
            >
              상세 프로필 보기
            </a>
          </div>
        </div>
        <button
          type="button"
          onClick={onEdit}
          aria-label="환자 정보 편집"
          disabled={isReadOnly}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-[#4d5874] transition hover:bg-[#edf5ff] hover:text-[#2563eb] disabled:cursor-not-allowed disabled:text-[#c7d1df]"
        >
          <Edit3 className="h-5 w-5" />
        </button>
      </div>
    </Panel>
  );
}

function InfoTag({ label }: { label: string }) {
  return (
    <span className="rounded-md bg-[#f3f6fb] px-2.5 py-1 text-xs font-extrabold text-[#59657a]">
      {label}
    </span>
  );
}

export function EmptyPatientPanel() {
  return (
    <Panel>
      <div className="px-5 py-12 text-center">
        <p className="text-base font-extrabold text-[#151b28]">
          대기 중인 환자가 없습니다.
        </p>
        <p className="mt-2 text-sm font-bold text-[#8a94a6]">
          대기열에서 환자를 선택하면 EMR 정보가 표시됩니다.
        </p>
      </div>
    </Panel>
  );
}

export function HistoryPanel({ histories }: { histories: EmrResult["emr_history"] }) {
  return (
    <Panel>
      <div className="border-b border-[#edf1f6] px-5 py-3">
        <h2 className="text-base font-extrabold text-[#151b28]">
          과거 문진 기록
        </h2>
      </div>
      <div className="max-h-[270px] space-y-3 overflow-y-auto px-5 py-4">
        {histories.length === 0 && (
          <div className="rounded-lg bg-[#f8fafc] px-4 py-8 text-center text-sm font-bold text-[#8a94a6]">
            과거 문진 기록이 없습니다.
          </div>
        )}
        {histories.map((history) => (
          <article
            key={history.emr_id}
            className="grid grid-cols-[120px_1fr_280px] gap-4 rounded-lg border border-[#e8edf4] p-4"
          >
            <div>
              <p className="text-sm font-extrabold tabular-nums text-[#4d5874]">
                {history.date}
              </p>
              <p className="mt-2 text-xs font-bold text-[#8a94a6]">
                {history.doctor_name}
              </p>
            </div>
            <p className="text-sm font-bold leading-6 text-[#4d5874]">
              {history.vet_memo}
            </p>
            <div className="rounded-lg bg-[#f8fafc] p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-extrabold text-[#2563eb]">처방전</p>
                {history.prescriptions.length > 2 && (
                  <button
                    type="button"
                    className="text-xs font-extrabold text-[#59657a]"
                  >
                    펼치기
                  </button>
                )}
              </div>
              <div className="space-y-2">
                {history.prescriptions.slice(0, 2).map((prescription) => (
                  <PrescriptionLine
                    key={`${history.emr_id}-${prescription.drug_name}`}
                    prescription={prescription}
                  />
                ))}
              </div>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}

function PrescriptionLine({ prescription }: { prescription: Prescription }) {
  return (
    <div className="grid grid-cols-[1fr_46px_46px_46px_42px] gap-2 text-xs font-bold text-[#4d5874]">
      <span className="truncate font-extrabold">{prescription.drug_name}</span>
      <span>{prescription.dosage}</span>
      <span>{prescription.form}</span>
      <span>{prescription.frequency}</span>
      <span>{prescription.duration_days}일</span>
    </div>
  );
}
