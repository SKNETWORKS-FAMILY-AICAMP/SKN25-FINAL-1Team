import { Loader2 } from "lucide-react";
import type { PetInfo, Prescription } from "../../types/emr";
import { Panel } from "./EmrShared";

export function AutoPrescriptionPanel({
  patient,
  prescriptions,
  isLoading = false,
  onOpenPreview,
  previewErrorMessage = null,
  isReadOnly = false,
}: {
  patient?: PetInfo;
  prescriptions: Prescription[];
  isLoading?: boolean;
  onOpenPreview: () => void;
  previewErrorMessage?: string | null;
  isReadOnly?: boolean;
}) {
  return (
    <Panel className="fixed right-4 top-[96px] h-[calc(100vh-112px)] w-[320px] overflow-hidden">
      <div className="px-5 py-4">
        <h2 className="text-lg font-extrabold text-[#151b28]">처방전 요약</h2>
      </div>
      <div className="space-y-4 px-5">
        {patient && (
          <p className="text-sm font-extrabold text-[#4d5874]">
            {patient.pet_name} {patient.gender === "Female" ? "♀" : "♂"} (
            {patient.species}, {patient.weight_kg}kg, {patient.age}살)
          </p>
        )}

        {isLoading ? (
          <div className="rounded-lg border border-[#e8edf4] px-4 py-8 text-center text-sm text-[#a8b0bf]">
            <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-[#64748b]" strokeWidth={2.1} />
            AI가 처방전을 생성하고 있습니다...
          </div>
        ) : prescriptions.length === 0 ? (
          <div
            className={`rounded-lg border px-4 py-8 text-center text-sm ${
              previewErrorMessage
                ? "border-red-200 bg-red-50 text-red-600"
                : "border-[#e8edf4] text-[#a8b0bf]"
            }`}
          >
            <p className="font-extrabold">
              {previewErrorMessage || "처방전 항목이 아직 없습니다."}
            </p>
            <p className={`mt-1 text-xs font-bold ${previewErrorMessage ? "text-red-500" : ""}`}>
              자동 생성하거나 약제를 검색해 추가하세요.
            </p>
          </div>
        ) : (
          <div className="max-h-[calc(100vh-330px)] space-y-2 overflow-y-auto pr-1">
            {prescriptions.map((prescription, index) => (
              <div
                key={prescription.client_id ?? `${prescription.drug_name}-${index}`}
                className="rounded-lg border border-[#e8edf4] bg-white px-3 py-3"
              >
                <p className="break-words text-sm font-extrabold leading-5 text-[#20283a]">
                  {prescription.drug_name}
                </p>
                <div className="mt-2 grid grid-cols-[52px_1fr] gap-x-2 gap-y-1 text-xs font-bold leading-5 text-[#4d5874]">
                  <span className="text-[#8a94a6]">형태</span>
                  <span className="break-words">{prescription.form || "-"}</span>
                  <span className="text-[#8a94a6]">용량</span>
                  <span className="break-words">
                    {prescription.dosage?.replace(/체중\s*[\d.]+kg\s*기준\s*/g, "") || "-"}
                    {prescription.duration_days ? ` / ${prescription.duration_days}일` : ""}
                  </span>
                  <span className="text-[#8a94a6]">용법</span>
                  <span className="break-words">{prescription.frequency || "-"}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="absolute inset-x-0 bottom-0 border-t border-[#edf1f6] bg-white p-4">
        <div className="flex">
          <button
            type="button"
            onClick={onOpenPreview}
            disabled={isReadOnly}
            className="h-10 w-full rounded-lg border border-[#dfe6f1] text-sm font-extrabold text-[#4d5874] disabled:cursor-not-allowed disabled:bg-[#f8fafc] disabled:text-[#a8b0bf]"
          >
            미리보기
          </button>
        </div>
      </div>
    </Panel>
  );
}
