import { useCallback, useEffect, useMemo, useState } from "react";
import type { DrugSearchResult } from "../api/prescriptionApi";
import { apiClient } from "../api/client";
import { FORM_OPTIONS, DOSAGE_OPTIONS, FREQUENCY_OPTIONS, DURATION_OPTIONS } from "../components/emr/EditorPanels";
import { fetchEmrQueue, fetchEmrDetail, fetchEmrReport, fetchDoctorFollowup, generateAutoPrescription, uploadEmrFile } from "../api/emrApi";
import type { ValidationResultResponse, FollowupItem } from "../api/emrApi";
import { updateReservationStatus } from "../api/reservationApi";
import { useAuthStore } from "../stores/auth-store";
import type { AuthState } from "../stores/auth-store";
import type {
  IntakeApplyTarget,
  Prescription,
  PreviewImage,
  QueuePatient,
  QueueTab,
  EmrResult,
  UploadedFile,
} from "../types/emr";

const DATE_MS = 24 * 60 * 60 * 1000;
let prescriptionClientIdSeq = 0;

function snapToStringOption(value: string, options: string[]): string {
  if (options.includes(value)) return value;
  const startsWith = options.find((o) => o.toLowerCase().startsWith(value.toLowerCase()));
  if (startsWith) return startsWith;
  const contains = options.find((o) => o.toLowerCase().includes(value.toLowerCase()));
  if (contains) return contains;
  return options[0];
}

function snapToDurationOption(days: number, options: number[]): number {
  return options.reduce((prev, curr) => (Math.abs(curr - days) < Math.abs(prev - days) ? curr : prev));
}

function makePrescriptionClientId() {
  prescriptionClientIdSeq += 1;
  return `prescription-${Date.now()}-${prescriptionClientIdSeq}`;
}

function toDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T00:00:00`);
  date.setDate(date.getDate() + days);
  return toDateInputValue(date);
}

function formatQueueDateLabel(dateValue: string) {
  const today = toDateInputValue(new Date());
  const diff =
    (new Date(`${dateValue}T00:00:00`).getTime() -
      new Date(`${today}T00:00:00`).getTime()) /
    DATE_MS;

  if (diff === 0) return "오늘";
  if (diff === -1) return "어제";
  if (diff === 1) return "내일";

  return new Date(`${dateValue}T00:00:00`).toLocaleDateString("ko-KR", {
    month: "long",
    day: "numeric",
  });
}

export function useEmrData() {
  const session = useAuthStore((s: AuthState) => s.session);
  const accessToken = session?.accessToken ?? "";

  const todayValue = toDateInputValue(new Date());
  const [selectedDate, setSelectedDateState] = useState(todayValue);
  const [queueTab, setQueueTab] = useState<QueueTab>("waiting");
  const [waitingQueue, setWaitingQueue] = useState<QueuePatient[]>([]);
  const [completedQueue, setCompletedQueue] = useState<QueuePatient[]>([]);
  const [isLoadingQueue, setIsLoadingQueue] = useState(false);

  const [selectedScheduleId, setSelectedScheduleId] = useState<number | undefined>(undefined);
  const [currentEmr, setCurrentEmr] = useState<EmrResult | undefined>(undefined);
  const [isLoadingEmr, setIsLoadingEmr] = useState(false);

  const [editorValue, setEditorValue] = useState("");
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [completeVisitError, setCompleteVisitError] = useState<string | null>(null);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [isLoadingAutoPresc, setIsLoadingAutoPresc] = useState(false);
  const [autoPrescriptionError, setAutoPrescriptionError] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResultResponse["result"]>(null);
  const [followupItems, setFollowupItems] = useState<FollowupItem[]>([]);
  const [isAutoPanelOpen, setIsAutoPanelOpen] = useState(true);
  const [isPrescriptionPreviewOpen, setIsPrescriptionPreviewOpen] = useState(false);
  const [isProfileEditOpen, setIsProfileEditOpen] = useState(false);
  const [previewImage, setPreviewImage] = useState<PreviewImage | null>(null);
  const [lastRefreshText, setLastRefreshText] = useState("방금 전");
  const isTodayView = selectedDate === todayValue;

  const clearEditableState = useCallback(() => {
    setEditorValue("");
    setUploadedFiles([]);
    setUploadError(null);
    setCompleteVisitError(null);
    setPrescriptions([]);
    setAutoPrescriptionError(null);
    setIsPrescriptionPreviewOpen(false);
    setIsProfileEditOpen(false);
  }, []);

  // ── EMR Queue 로드 ──────────────────────────────
  const loadQueue = useCallback(async () => {
    if (!accessToken) return;
    setIsLoadingQueue(true);
    try {
      const result = await fetchEmrQueue({ accessToken, date: selectedDate });
      setWaitingQueue(result.waiting);
      setCompletedQueue(result.completed);

      setSelectedScheduleId((prev: number | undefined) => {
        const combined = [...result.waiting, ...result.completed];
        if (prev !== undefined && combined.some((p) => p.schedule_id === prev)) {
          return prev;
        }
        return result.waiting[0]?.schedule_id ?? result.completed[0]?.schedule_id;
      });
    } catch (err) {
      console.error("[EMR Queue] fetch failed:", err);
    } finally {
      setIsLoadingQueue(false);
      setLastRefreshText(
        new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
      );
    }
  }, [accessToken, selectedDate]);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  // ── EMR Detail + Validation + Followup 로드 ────────────────
  useEffect(() => {
    if (selectedScheduleId === undefined || !accessToken) {
      setCurrentEmr(undefined);
      setValidationResult(null);
      setPrescriptions([]);
      setAutoPrescriptionError(null);
      setCompleteVisitError(null);
      setFollowupItems([]);
      return;
    }
    const selectedEmrid = [...waitingQueue, ...completedQueue].find(
      (p) => p.schedule_id === selectedScheduleId,
    )?.emrid;

    let cancelled = false;
    setIsLoadingEmr(true);
    // validation/judge는 내부 관리용이라 수의사 UI에는 노출하지 않는다(프론트에서 조회하지 않음).
    Promise.all([
      fetchEmrDetail({ accessToken, scheduleId: selectedScheduleId }),
      selectedEmrid !== undefined
        ? fetchDoctorFollowup({ accessToken, emrid: selectedEmrid }).catch(() => [])
        : Promise.resolve([]),
    ])
      .then(([emr, followups]) => {
        if (!cancelled) {
          setCurrentEmr(emr);
          setFollowupItems(followups);
        }
      })
      .catch((err: unknown) => {
        console.error("[EMR Detail] fetch failed:", err);
        if (!cancelled) {
          setCurrentEmr(undefined);
          setValidationResult(null);
          setFollowupItems([]);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingEmr(false);
      });
    return () => { cancelled = true; };
  }, [selectedScheduleId, accessToken, waitingQueue, completedQueue]);

  // ── 파생 상태 ────────────────────────────────────
  const currentQueue = queueTab === "waiting" ? waitingQueue : completedQueue;

  const currentAttachments = currentEmr?.triage_summary.attachments ?? [];
  const visibleGuardianFiles = currentAttachments.slice(0, 4);
  const hiddenGuardianFileCount = Math.max(currentAttachments.length - 4, 0);
  const completedCount = completedQueue.length;
  const queueDateLabel = formatQueueDateLabel(selectedDate);

  const queueTitle = useMemo(
    () =>
      queueTab === "waiting"
        ? `${queueDateLabel} ${waitingQueue.length}건 대기 중`
        : `${queueDateLabel} ${completedCount}건 진료 완료`,
    [completedCount, queueDateLabel, queueTab, waitingQueue.length]
  );

  // ── 핸들러 ────────────────────────────────────────
  const handleRefreshQueue = useCallback(() => {
    loadQueue();
  }, [loadQueue]);

  const handleChangeDate = useCallback((dateValue: string) => {
    if (!dateValue) return;
    setSelectedDateState(dateValue);
    setSelectedScheduleId(undefined);
    setValidationResult(null);
    setFollowupItems([]);
    clearEditableState();
  }, [clearEditableState]);

  const handleMoveDate = useCallback((days: number) => {
    handleChangeDate(addDays(selectedDate, days));
  }, [handleChangeDate, selectedDate]);

  const handleGoToday = useCallback(() => {
    handleChangeDate(toDateInputValue(new Date()));
  }, [handleChangeDate]);

  const handleChangeTab = useCallback((tab: QueueTab) => {
    setQueueTab(tab);
    const queue = tab === "waiting" ? waitingQueue : completedQueue;
    setSelectedScheduleId(queue[0]?.schedule_id);
  }, [waitingQueue, completedQueue]);

  const handleCompleteVisit = useCallback(async () => {
    if (!isTodayView || selectedScheduleId === undefined) return;

    const targetPatient = waitingQueue.find(
      (p: QueuePatient) => p.schedule_id === selectedScheduleId
    );
    if (!targetPatient) return;

    setCompleteVisitError(null);

    // API: 상태 업데이트 (처방전 포함)
    try {
      await updateReservationStatus(selectedScheduleId, "진료완료", {
        vet_memo: editorValue,
        attachments: uploadedFiles,
        prescriptions: prescriptions.length > 0 ? prescriptions.map((p) => ({
          drug_name: p.drug_name,
          form: p.form,
          dosage: p.dosage,
          duration_days: p.duration_days,
        })) : undefined,
      });
    } catch (err) {
      console.error("[CompleteVisit] status update failed:", err);
      setCompleteVisitError("진료 완료 처리에 실패했습니다. 잠시 후 다시 시도해주세요.");
      return;
    }

    // 로컬 큐 업데이트
    const nextWaiting = waitingQueue.filter(
      (p: QueuePatient) => p.schedule_id !== selectedScheduleId
    );
    setWaitingQueue(nextWaiting);
    setCompletedQueue((prev: QueuePatient[]) => [targetPatient, ...prev]);
    setSelectedScheduleId(nextWaiting[0]?.schedule_id);
    setEditorValue("");
    setCompleteVisitError(null);
    setPrescriptions([]);
    setAutoPrescriptionError(null);
    setUploadedFiles([]);
  }, [editorValue, isTodayView, prescriptions, selectedScheduleId, uploadedFiles, waitingQueue]);

  const handleApplyIntake = useCallback((target: IntakeApplyTarget) => {
    if (!isTodayView) return;

    const summary = currentEmr?.triage_summary.summary ?? [];
    const memo = currentEmr?.triage_summary.memo;

    const selectedTexts = [
      target !== "memo" && summary.length > 0
        ? summary.map((b: string) => `- ${b}`).join("\n")
        : "",
      target !== "summary" && memo ? memo : "",
    ].filter(Boolean);

    setEditorValue((prev: string) =>
      [prev, ...selectedTexts].filter(Boolean).join("\n\n")
    );
  }, [currentEmr, isTodayView]);

  const handleRemoveFile = useCallback((fileId: number) => {
    setUploadedFiles((files: UploadedFile[]) =>
      files.filter((f: UploadedFile) => f.id !== fileId)
    );
  }, []);

  const handleUploadFile = useCallback(
    async (file: File) => {
      if (!isTodayView) return;

      setUploadError(null);
      setIsUploadingFile(true);
      try {
        const { cloudfront_url } = await uploadEmrFile({ accessToken, file });
        setUploadedFiles((files: UploadedFile[]) => [
          ...files,
          {
            id: Date.now(),
            label: file.name,
            url: cloudfront_url,
          },
        ]);
      } catch (err: unknown) {
        console.error("[UploadEmrFile] failed:", err);
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 413) {
          setUploadError("파일 크기는 50MB 이하만 업로드 가능합니다.");
        } else {
          setUploadError("사진 업로드에 실패했습니다. 다시 시도해주세요.");
        }
      } finally {
        setIsUploadingFile(false);
      }
    },
    [accessToken, isTodayView]
  );

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
      const mapped: Prescription[] = meds.map((m) => ({
        client_id: makePrescriptionClientId(),
        drug_name: m.name ?? "",
        dosage: m.dosage ?? "",
        form: m.route ?? "",
        frequency: m.frequency ?? "",
        duration_days: parseInt(m.duration ?? "0", 10) || 0,
      }));
      setPrescriptions(mapped);
    } catch (err) {
      console.error("[AutoPrescription] fetch failed:", err);
      setPrescriptions([]);
      setAutoPrescriptionError("처방전 자동 생성에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setIsLoadingAutoPresc(false);
    }
  }, [selectedScheduleId, accessToken, isTodayView]);

  const handleRemovePrescription = useCallback((clientId: string) => {
    if (!isTodayView) return;
    setPrescriptions((items: Prescription[]) =>
      items.filter((item: Prescription, index) => (item.client_id ?? `${item.drug_name}-${index}`) !== clientId)
    );
  }, [isTodayView]);

  const handleUpdatePrescription = useCallback(
    (clientId: string, field: keyof Prescription, value: string | number) => {
      if (!isTodayView) return;
      setPrescriptions((items: Prescription[]) =>
        items.map((item: Prescription, index) =>
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

  const handleResetToWaiting = useCallback(async () => {
    if (!isTodayView || selectedScheduleId === undefined) return;
    const targetPatient = completedQueue.find(
      (p: QueuePatient) => p.schedule_id === selectedScheduleId
    );
    if (!targetPatient) return;
    try {
      await apiClient.post(
        `/doctor/emr/${selectedScheduleId}/reset`,
        {},
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
      setCompletedQueue((prev: QueuePatient[]) =>
        prev.filter((p: QueuePatient) => p.schedule_id !== selectedScheduleId)
      );
      setWaitingQueue((prev: QueuePatient[]) => [...prev, targetPatient]);
      setQueueTab("waiting");
      setEditorValue("");
      setPrescriptions([]);
      setAutoPrescriptionError(null);
      // 기존 대기열 첫 번째 환자를 선택, 없으면 되돌린 환자 선택
      const nextId = waitingQueue[0]?.schedule_id ?? targetPatient.schedule_id;
      if (nextId === selectedScheduleId) {
        // 같은 id면 useEffect가 재실행되지 않으므로 undefined 거쳐서 강제 트리거
        setSelectedScheduleId(undefined);
        setTimeout(() => setSelectedScheduleId(nextId), 0);
      } else {
        setSelectedScheduleId(nextId);
      }
    } catch (err) {
      console.error("[ResetToWaiting] failed:", err);
    }
  }, [selectedScheduleId, completedQueue, waitingQueue, accessToken, isTodayView]);

  const handleGeneratePrescription = useCallback(async () => {
    if (!isTodayView || selectedScheduleId === undefined) return;
    setAutoPrescriptionError(null);
    setIsLoadingAutoPresc(true);
    try {
      const meds = await generateAutoPrescription({ accessToken, scheduleId: selectedScheduleId, doctorNotes: editorValue });
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

  const handleAddPrescription = useCallback((drug: DrugSearchResult) => {
    if (!isTodayView) return;
    setPrescriptions((items: Prescription[]) => {
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
  }, [isTodayView]);

  const openPreviewImage = useCallback((url: string, label: string) => {
    setPreviewImage({ url, label });
  }, []);

  const handlePetInfoSaved = useCallback((updated: Partial<EmrResult["pet_info"]>) => {
    setCurrentEmr((prev: EmrResult | undefined) => {
      if (!prev) return prev;
      return { ...prev, pet_info: { ...prev.pet_info, ...updated } };
    });
  }, []);

  return {
    selectedDate,
    isTodayView,
    queueTab,
    waitingQueue,
    completedQueue,
    selectedScheduleId,
    editorValue,
    uploadedFiles,
    isUploadingFile,
    uploadError,
    completeVisitError,
    prescriptions,
    isLoadingAutoPresc,
    autoPrescriptionError,
    validationResult,
    followupItems,
    isAutoPanelOpen,
    isPrescriptionPreviewOpen,
    isProfileEditOpen,
    previewImage,
    lastRefreshText,
    isLoadingQueue,
    isLoadingEmr,
    currentQueue,
    currentEmr,
    visibleGuardianFiles,
    hiddenGuardianFileCount,
    queueTitle,
    setQueueTab,
    setSelectedScheduleId,
    setEditorValue,
    setIsAutoPanelOpen,
    setIsPrescriptionPreviewOpen,
    setIsProfileEditOpen,
    setPreviewImage,
    handleChangeDate,
    handleMoveDate,
    handleGoToday,
    handleRefreshQueue,
    handleChangeTab,
    handleCompleteVisit,
    handleApplyIntake,
    handleRemoveFile,
    handleUploadFile,
    handleLoadAutoPrescription,
    handleRemovePrescription,
    handleUpdatePrescription,
    handleClearAutoPrescription,
    handleGeneratePrescription,
    handleAddPrescription,
    handleResetToWaiting,
    openPreviewImage,
    handlePetInfoSaved,
  };
}
