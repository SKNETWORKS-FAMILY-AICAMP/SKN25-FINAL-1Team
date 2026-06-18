import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { fetchEmrDetail, fetchDoctorFollowup } from "../api/emrApi";
import type { ValidationResultResponse, FollowupItem } from "../api/emrApi";
import { updateReservationStatus } from "../api/reservationApi";
import { useAuthStore } from "../stores/auth-store";
import type { AuthState } from "../stores/auth-store";
import type { IntakeApplyTarget, PreviewImage, QueuePatient, EmrResult } from "../types/emr";
import { useEmrQueue, toDateInputValue, addDays } from "./useEmrQueue";
import { useEmrFile } from "./useEmrFile";
import { useEmrPrescription } from "./useEmrPrescription";
import { logger } from "../utils/logger";

export function useEmrData() {
  const session = useAuthStore((s: AuthState) => s.session);
  const accessToken = session?.accessToken ?? "";

  const queue = useEmrQueue(accessToken);
  const { isTodayView, selectedScheduleId, waitingQueue, completedQueue } = queue;

  const [editorValue, setEditorValue] = useState("");
  const [completeVisitError, setCompleteVisitError] = useState<string | null>(null);
  const [isProfileEditOpen, setIsProfileEditOpen] = useState(false);
  const [previewImage, setPreviewImage] = useState<PreviewImage | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResultResponse["result"]>(null);
  const [followupItems, setFollowupItems] = useState<FollowupItem[]>([]);
  const [isAutoPanelOpen, setIsAutoPanelOpen] = useState(true);
  const [isLoadingEmr, setIsLoadingEmr] = useState(false);
  const [currentEmr, setCurrentEmr] = useState<EmrResult | undefined>(undefined);

  const file = useEmrFile(accessToken, isTodayView);
  const prescription = useEmrPrescription(accessToken, isTodayView, selectedScheduleId, editorValue);

  // ── 날짜/큐 관련 핸들러 ────────────────────────────
  const clearEditableState = useCallback(() => {
    setEditorValue("");
    setCompleteVisitError(null);
    setIsProfileEditOpen(false);
    file.clear();
    prescription.clear();
  }, [file, prescription]);

  const handleChangeDate = useCallback(
    (dateValue: string) => {
      if (!dateValue) return;
      queue.setSelectedDate(dateValue);
      queue.setSelectedScheduleId(undefined);
      setValidationResult(null);
      setFollowupItems([]);
      clearEditableState();
    },
    [queue, clearEditableState]
  );

  const handleMoveDate = useCallback(
    (days: number) => handleChangeDate(addDays(queue.selectedDate, days)),
    [handleChangeDate, queue.selectedDate]
  );

  const handleGoToday = useCallback(
    () => handleChangeDate(toDateInputValue(new Date())),
    [handleChangeDate]
  );

  const handleRefreshQueue = useCallback(() => queue.loadQueue(), [queue]);

  // ── EMR Detail + Followup 로드 ──────────────────────
  useEffect(() => {
    if (selectedScheduleId === undefined || !accessToken) {
      setCurrentEmr(undefined);
      setValidationResult(null);
      setFollowupItems([]);
      return;
    }
    const selectedEmrid = [...waitingQueue, ...completedQueue].find(
      (p) => p.schedule_id === selectedScheduleId
    )?.emrid;

    let cancelled = false;
    setIsLoadingEmr(true);
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
        logger.error("[EMR Detail] fetch failed:", err);
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

  // ── 파생 상태 ──────────────────────────────────────
  const currentAttachments = currentEmr?.triage_summary.attachments ?? [];
  const visibleGuardianFiles = currentAttachments.slice(0, 4);
  const hiddenGuardianFileCount = Math.max(currentAttachments.length - 4, 0);

  // ── 핸들러 ────────────────────────────────────────
  const handleCompleteVisit = useCallback(async () => {
    if (!isTodayView || selectedScheduleId === undefined) return;

    const targetPatient = waitingQueue.find(
      (p: QueuePatient) => p.schedule_id === selectedScheduleId
    );
    if (!targetPatient) return;

    setCompleteVisitError(null);

    try {
      await updateReservationStatus(selectedScheduleId, "진료완료", {
        vet_memo: editorValue,
        attachments: file.uploadedFiles,
        prescriptions:
          prescription.prescriptions.length > 0
            ? prescription.prescriptions.map((p) => ({
                drug_name: p.drug_name,
                form: p.form,
                dosage: p.dosage,
                duration_days: p.duration_days,
              }))
            : undefined,
      });
    } catch (err) {
      logger.error("[CompleteVisit] status update failed:", err);
      setCompleteVisitError("진료 완료 처리에 실패했습니다. 잠시 후 다시 시도해주세요.");
      return;
    }

    const nextWaiting = waitingQueue.filter(
      (p: QueuePatient) => p.schedule_id !== selectedScheduleId
    );
    queue.setWaitingQueue(nextWaiting);
    queue.setCompletedQueue((prev: QueuePatient[]) => [targetPatient, ...prev]);
    queue.setSelectedScheduleId(nextWaiting[0]?.schedule_id);
    setEditorValue("");
    setCompleteVisitError(null);
    prescription.setPrescriptions([]);
    prescription.setAutoPrescriptionError(null);
    file.setUploadedFiles([]);
  }, [editorValue, isTodayView, prescription, selectedScheduleId, file, waitingQueue, queue]);

  const handleApplyIntake = useCallback(
    (target: IntakeApplyTarget) => {
      if (!isTodayView) return;
      const summary = currentEmr?.triage_summary.summary ?? [];
      const memo = currentEmr?.triage_summary.memo;
      const selectedTexts = [
        target !== "memo" && summary.length > 0
          ? summary.map((b: string) => `- ${b}`).join("\n")
          : "",
        target !== "summary" && memo ? memo : "",
      ].filter(Boolean);
      setEditorValue((prev) => [prev, ...selectedTexts].filter(Boolean).join("\n\n"));
    },
    [currentEmr, isTodayView]
  );

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
      queue.setCompletedQueue((prev: QueuePatient[]) =>
        prev.filter((p: QueuePatient) => p.schedule_id !== selectedScheduleId)
      );
      queue.setWaitingQueue((prev: QueuePatient[]) => [...prev, targetPatient]);
      queue.setQueueTab("waiting");
      setEditorValue("");
      prescription.setPrescriptions([]);
      prescription.setAutoPrescriptionError(null);
      const nextId = waitingQueue[0]?.schedule_id ?? targetPatient.schedule_id;
      if (nextId === selectedScheduleId) {
        queue.setSelectedScheduleId(undefined);
        setTimeout(() => queue.setSelectedScheduleId(nextId), 0);
      } else {
        queue.setSelectedScheduleId(nextId);
      }
    } catch (err) {
      logger.error("[ResetToWaiting] failed:", err);
    }
  }, [selectedScheduleId, completedQueue, waitingQueue, accessToken, isTodayView, queue, prescription]);

  const openPreviewImage = useCallback((url: string, label: string) => {
    setPreviewImage({ url, label });
  }, []);

  const handlePetInfoSaved = useCallback((updated: Partial<EmrResult["pet_info"]>) => {
    setCurrentEmr((prev) => {
      if (!prev) return prev;
      return { ...prev, pet_info: { ...prev.pet_info, ...updated } };
    });
  }, []);

  return {
    // Queue
    selectedDate: queue.selectedDate,
    isTodayView: queue.isTodayView,
    queueTab: queue.queueTab,
    setQueueTab: queue.setQueueTab,
    waitingQueue: queue.waitingQueue,
    completedQueue: queue.completedQueue,
    selectedScheduleId: queue.selectedScheduleId,
    setSelectedScheduleId: queue.setSelectedScheduleId,
    isLoadingQueue: queue.isLoadingQueue,
    lastRefreshText: queue.lastRefreshText,
    currentQueue: queue.currentQueue,
    queueTitle: queue.queueTitle,
    handleChangeTab: queue.handleChangeTab,
    handleChangeDate,
    handleMoveDate,
    handleGoToday,
    handleRefreshQueue,
    doctors: queue.doctors,
    selectedDoctorId: queue.selectedDoctorId,
    setSelectedDoctorId: queue.setSelectedDoctorId,
    // File
    uploadedFiles: file.uploadedFiles,
    isUploadingFile: file.isUploadingFile,
    uploadError: file.uploadError,
    handleRemoveFile: file.handleRemoveFile,
    handleUploadFile: file.handleUploadFile,
    // Prescription
    prescriptions: prescription.prescriptions,
    isLoadingAutoPresc: prescription.isLoadingAutoPresc,
    autoPrescriptionError: prescription.autoPrescriptionError,
    isPrescriptionPreviewOpen: prescription.isPrescriptionPreviewOpen,
    setIsPrescriptionPreviewOpen: prescription.setIsPrescriptionPreviewOpen,
    handleLoadAutoPrescription: prescription.handleLoadAutoPrescription,
    handleGeneratePrescription: prescription.handleGeneratePrescription,
    handleAddPrescription: prescription.handleAddPrescription,
    handleRemovePrescription: prescription.handleRemovePrescription,
    handleUpdatePrescription: prescription.handleUpdatePrescription,
    handleClearAutoPrescription: prescription.handleClearAutoPrescription,
    // EMR detail
    isLoadingEmr,
    currentEmr,
    validationResult,
    followupItems,
    visibleGuardianFiles,
    hiddenGuardianFileCount,
    // Editor
    editorValue,
    setEditorValue,
    completeVisitError,
    // UI state
    isAutoPanelOpen,
    setIsAutoPanelOpen,
    isProfileEditOpen,
    setIsProfileEditOpen,
    previewImage,
    setPreviewImage,
    // Handlers
    handleCompleteVisit,
    handleApplyIntake,
    handleResetToWaiting,
    openPreviewImage,
    handlePetInfoSaved,
  };
}
