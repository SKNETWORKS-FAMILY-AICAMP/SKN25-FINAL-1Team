import { useCallback, useEffect, useMemo, useState } from "react";
import type { DrugSearchResult } from "../api/prescriptionApi";
import { apiClient } from "../api/client";
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

export function useEmrData() {
  const session = useAuthStore((s: AuthState) => s.session);
  const accessToken = session?.accessToken ?? "";

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
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [autoPrescriptions, setAutoPrescriptions] = useState<Prescription[]>([]);
  const [isLoadingAutoPresc, setIsLoadingAutoPresc] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResultResponse["result"]>(null);
  const [followupItems, setFollowupItems] = useState<FollowupItem[]>([]);
  const [isAutoPanelOpen, setIsAutoPanelOpen] = useState(true);
  const [isPrescriptionPreviewOpen, setIsPrescriptionPreviewOpen] = useState(false);
  const [isProfileEditOpen, setIsProfileEditOpen] = useState(false);
  const [previewImage, setPreviewImage] = useState<PreviewImage | null>(null);
  const [lastRefreshText, setLastRefreshText] = useState("방금 전");

  // ── EMR Queue 로드 ──────────────────────────────
  const loadQueue = useCallback(async () => {
    if (!accessToken) return;
    setIsLoadingQueue(true);
    try {
      const result = await fetchEmrQueue({ accessToken });
      setWaitingQueue(result.waiting);
      setCompletedQueue(result.completed);

      // 첫 로드 시 대기 첫 번째 환자 자동 선택
      setSelectedScheduleId((prev: number | undefined) => {
        if (prev !== undefined) return prev;
        return result.waiting[0]?.schedule_id;
      });
    } catch (err) {
      console.error("[EMR Queue] fetch failed:", err);
    } finally {
      setIsLoadingQueue(false);
      setLastRefreshText(
        new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
      );
    }
  }, [accessToken]);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  // ── EMR Detail + Validation + Followup 로드 ────────────────
  useEffect(() => {
    if (selectedScheduleId === undefined || !accessToken) {
      setCurrentEmr(undefined);
      setValidationResult(null);
      setAutoPrescriptions([]);
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

  const queueTitle = useMemo(
    () =>
      queueTab === "waiting"
        ? `오늘 ${waitingQueue.length}건 대기 중`
        : `오늘 ${completedCount}건 진료 완료`,
    [completedCount, queueTab, waitingQueue.length]
  );

  // ── 핸들러 ────────────────────────────────────────
  const handleRefreshQueue = useCallback(() => {
    loadQueue();
  }, [loadQueue]);

  const handleChangeTab = useCallback((tab: QueueTab) => {
    setQueueTab(tab);
    const queue = tab === "waiting" ? waitingQueue : completedQueue;
    setSelectedScheduleId(queue[0]?.schedule_id);
  }, [waitingQueue, completedQueue]);

  const handleCompleteVisit = useCallback(async () => {
    if (selectedScheduleId === undefined) return;

    const targetPatient = waitingQueue.find(
      (p: QueuePatient) => p.schedule_id === selectedScheduleId
    );
    if (!targetPatient) return;

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
    }

    // 로컬 큐 업데이트
    const nextWaiting = waitingQueue.filter(
      (p: QueuePatient) => p.schedule_id !== selectedScheduleId
    );
    setWaitingQueue(nextWaiting);
    setCompletedQueue((prev: QueuePatient[]) => [targetPatient, ...prev]);
    setSelectedScheduleId(nextWaiting[0]?.schedule_id);
    setEditorValue("");
    setPrescriptions([]);
    setUploadedFiles([]);
  }, [editorValue, selectedScheduleId, uploadedFiles, waitingQueue]);

  const handleApplyIntake = useCallback((target: IntakeApplyTarget) => {
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
  }, [currentEmr]);

  const handleRemoveFile = useCallback((fileId: number) => {
    setUploadedFiles((files: UploadedFile[]) =>
      files.filter((f: UploadedFile) => f.id !== fileId)
    );
  }, []);

  const handleUploadFile = useCallback(
    async (file: File) => {
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
      } catch (err) {
        console.error("[UploadEmrFile] failed:", err);
        setUploadError("사진 업로드에 실패했습니다. 다시 시도해주세요.");
      } finally {
        setIsUploadingFile(false);
      }
    },
    [accessToken]
  );

  const handleLoadAutoPrescription = useCallback(async () => {
    if (selectedScheduleId === undefined) return;
    setIsLoadingAutoPresc(true);
    try {
      const report = await fetchEmrReport({ accessToken, scheduleId: selectedScheduleId });
      if (!report?.ai_draft_json) {
        setAutoPrescriptions([]);
        return;
      }
      const draft = report.ai_draft_json as {
        prescription_draft?: { medications?: Array<Record<string, string>> };
      };
      const meds = draft.prescription_draft?.medications ?? [];
      const mapped: Prescription[] = meds.map((m) => ({
        drug_name: m.name ?? "",
        dosage: m.dosage ?? "",
        form: m.route ?? "",
        frequency: m.frequency ?? "",
        duration_days: parseInt(m.duration ?? "0", 10) || 0,
      }));
      setAutoPrescriptions(mapped);
      if (mapped.length > 0) setPrescriptions(mapped);
    } catch (err) {
      console.error("[AutoPrescription] fetch failed:", err);
      setAutoPrescriptions([]);
    } finally {
      setIsLoadingAutoPresc(false);
    }
  }, [selectedScheduleId, accessToken]);

  const handleRemovePrescription = useCallback((name: string) => {
    setPrescriptions((items: Prescription[]) =>
      items.filter((item: Prescription) => item.drug_name !== name)
    );
  }, []);

  const handleUpdatePrescription = useCallback(
    (drug_name: string, field: keyof Prescription, value: string | number) => {
      setPrescriptions((items: Prescription[]) =>
        items.map((item: Prescription) =>
          item.drug_name === drug_name ? { ...item, [field]: value } : item
        )
      );
    },
    []
  );

  const handleSavePrescription = useCallback(() => {
    setAutoPrescriptions(prescriptions);
  }, [prescriptions]);

  const handleClearAutoPrescription = useCallback(() => {
    setAutoPrescriptions([]);
  }, []);

  const handleResetToWaiting = useCallback(async () => {
    if (selectedScheduleId === undefined) return;
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
      setAutoPrescriptions([]);
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
  }, [selectedScheduleId, completedQueue, waitingQueue, accessToken]);

  const handleApplyAutoPrescription = useCallback(() => {
    if (autoPrescriptions.length === 0) return;
    setPrescriptions(autoPrescriptions);
    const text = [
      "[처방전]",
      ...autoPrescriptions.map(
        (p) => `- ${p.drug_name} / ${p.form} / ${p.dosage} / ${p.duration_days}일`
      ),
    ].join("\n");
    setEditorValue((prev: string) => [prev, text].filter(Boolean).join("\n\n"));
  }, [autoPrescriptions]);

  const handleGeneratePrescription = useCallback(async () => {
    if (selectedScheduleId === undefined) return;
    setAutoPrescriptions([]);
    setIsLoadingAutoPresc(true);
    try {
      const meds = await generateAutoPrescription({ accessToken, scheduleId: selectedScheduleId });
      setAutoPrescriptions(
        meds.map((m) => ({
          drug_name: m.drug_name,
          form: m.form,
          dosage: m.dosage,
          frequency: m.frequency,
          duration_days: m.duration_days,
        }))
      );
    } catch (err) {
      console.error("[GeneratePrescription] failed:", err);
      setAutoPrescriptions([]);
    } finally {
      setIsLoadingAutoPresc(false);
    }
  }, [selectedScheduleId, accessToken]);

  const handleAddPrescription = useCallback((drug: DrugSearchResult) => {
    setPrescriptions((items: Prescription[]) => {
      if (items.some((p) => p.drug_name === drug.name)) return items;
      return [
        ...items,
        {
          drug_name: drug.name,
          form: "",
          dosage: drug.dosage ?? "",
          frequency: "",
          duration_days: drug.duration_days ?? 0,
        },
      ];
    });
  }, []);

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
    queueTab,
    waitingQueue,
    completedQueue,
    selectedScheduleId,
    editorValue,
    uploadedFiles,
    isUploadingFile,
    uploadError,
    prescriptions,
    autoPrescriptions,
    isLoadingAutoPresc,
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
    handleRefreshQueue,
    handleChangeTab,
    handleCompleteVisit,
    handleApplyIntake,
    handleRemoveFile,
    handleUploadFile,
    handleLoadAutoPrescription,
    handleRemovePrescription,
    handleUpdatePrescription,
    handleSavePrescription,
    handleClearAutoPrescription,
    handleGeneratePrescription,
    handleAddPrescription,
    handleApplyAutoPrescription,
    handleResetToWaiting,
    openPreviewImage,
    handlePetInfoSaved,
  };
}
