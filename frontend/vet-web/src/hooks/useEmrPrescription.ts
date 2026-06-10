import { useCallback, useState } from "react";
import type { DrugSearchResult } from "../api/prescriptionApi";
import { fetchEmrReport, generateAutoPrescription } from "../api/emrApi";
import { FORM_OPTIONS, DOSAGE_OPTIONS, FREQUENCY_OPTIONS, DURATION_OPTIONS } from "../components/emr/EditorPanels";
import type { Prescription } from "../types/emr";

let prescriptionClientIdSeq = 0;

function makePrescriptionClientId() {
  prescriptionClientIdSeq += 1;
  return `prescription-${Date.now()}-${prescriptionClientIdSeq}`;
}

function snapToStringOption(value: string, options: string[]): string {
  if (options.includes(value)) return value;
  const startsWith = options.find((o) => o.toLowerCase().startsWith(value.toLowerCase()));
  if (startsWith) return startsWith;
  const contains = options.find((o) => o.toLowerCase().includes(value.toLowerCase()));
  if (contains) return contains;
  return options[0];
}

function snapToDurationOption(days: number, options: number[]): number {
  return options.reduce((prev, curr) =>
    Math.abs(curr - days) < Math.abs(prev - days) ? curr : prev
  );
}

export function useEmrPrescription(
  accessToken: string,
  isTodayView: boolean,
  selectedScheduleId: number | undefined,
  editorValue: string
) {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [isLoadingAutoPresc, setIsLoadingAutoPresc] = useState(false);
  const [autoPrescriptionError, setAutoPrescriptionError] = useState<string | null>(null);
  const [isPrescriptionPreviewOpen, setIsPrescriptionPreviewOpen] = useState(false);

  const clear = useCallback(() => {
    setPrescriptions([]);
    setAutoPrescriptionError(null);
    setIsPrescriptionPreviewOpen(false);
  }, []);

  const handleLoadAutoPrescription = useCallback(async () => {
    if (!isTodayView || selectedScheduleId === undefined) return;
    setAutoPrescriptionError(null);
    setIsLoadingAutoPresc(true);
    try {
      const report = await fetchEmrReport({ accessToken, scheduleId: selectedScheduleId });
      if (!report?.ai_draft_json) {
        setPrescriptions([]);
        return;
      }
      const draft = report.ai_draft_json as {
        prescription_draft?: { medications?: Array<Record<string, string>> };
      };
      const meds = draft.prescription_draft?.medications ?? [];
      setPrescriptions(
        meds.map((m) => ({
          client_id: makePrescriptionClientId(),
          drug_name: m.name ?? "",
          dosage: m.dosage ?? "",
          form: m.route ?? "",
          frequency: m.frequency ?? "",
          duration_days: parseInt(m.duration ?? "0", 10) || 0,
        }))
      );
    } catch (err) {
      console.error("[AutoPrescription] fetch failed:", err);
      setPrescriptions([]);
      setAutoPrescriptionError("처방전 자동 생성에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setIsLoadingAutoPresc(false);
    }
  }, [selectedScheduleId, accessToken, isTodayView]);

  const handleGeneratePrescription = useCallback(async () => {
    if (!isTodayView || selectedScheduleId === undefined) return;
    setAutoPrescriptionError(null);
    setIsLoadingAutoPresc(true);
    try {
      const meds = await generateAutoPrescription({
        accessToken,
        scheduleId: selectedScheduleId,
        doctorNotes: editorValue,
      });
      setPrescriptions(
        meds.map((m) => ({
          client_id: makePrescriptionClientId(),
          drug_name: m.drug_name,
          form: snapToStringOption(m.form, FORM_OPTIONS),
          dosage: snapToStringOption(m.dosage, DOSAGE_OPTIONS),
          frequency: snapToStringOption(m.frequency, FREQUENCY_OPTIONS),
          duration_days: snapToDurationOption(m.duration_days, DURATION_OPTIONS),
        }))
      );
    } catch (err) {
      console.error("[GeneratePrescription] failed:", err);
      setPrescriptions([]);
      setAutoPrescriptionError("처방전 자동 생성에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setIsLoadingAutoPresc(false);
    }
  }, [selectedScheduleId, accessToken, isTodayView, editorValue]);

  const handleAddPrescription = useCallback(
    (drug: DrugSearchResult) => {
      if (!isTodayView) return;
      setPrescriptions((items) => {
        if (items.some((p) => p.drug_name === drug.name)) return items;
        return [
          ...items,
          {
            drug_name: drug.name,
            form: "",
            dosage: drug.dosage ?? "",
            frequency: drug.usage_method ?? "",
            duration_days: drug.duration_days ?? 0,
            client_id: makePrescriptionClientId(),
            pil_seon: "선" as const,
          },
        ];
      });
    },
    [isTodayView]
  );

  const handleRemovePrescription = useCallback(
    (clientId: string) => {
      if (!isTodayView) return;
      setPrescriptions((items) =>
        items.filter(
          (item, index) => (item.client_id ?? `${item.drug_name}-${index}`) !== clientId
        )
      );
    },
    [isTodayView]
  );

  const handleUpdatePrescription = useCallback(
    (clientId: string, field: keyof Prescription, value: string | number) => {
      if (!isTodayView) return;
      setPrescriptions((items) =>
        items.map((item, index) =>
          (item.client_id ?? `${item.drug_name}-${index}`) === clientId
            ? { ...item, [field]: value }
            : item
        )
      );
    },
    [isTodayView]
  );

  const handleClearAutoPrescription = useCallback(() => {
    setPrescriptions([]);
  }, []);

  return {
    prescriptions,
    setPrescriptions,
    isLoadingAutoPresc,
    autoPrescriptionError,
    setAutoPrescriptionError,
    isPrescriptionPreviewOpen,
    setIsPrescriptionPreviewOpen,
    clear,
    handleLoadAutoPrescription,
    handleGeneratePrescription,
    handleAddPrescription,
    handleRemovePrescription,
    handleUpdatePrescription,
    handleClearAutoPrescription,
  };
}
