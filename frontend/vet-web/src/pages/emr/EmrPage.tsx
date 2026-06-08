import { TriangleAlert } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import {
  Group as ResizableGroup,
  Panel as ResizablePanel,
  Separator as ResizeSeparator,
} from "react-resizable-panels";
import { useLocation } from "react-router-dom";
import { AuthSession } from "../../api/authApi";
import type { FollowupItem } from "../../api/emrApi";
import { Button } from "../../components/common/Button";
import { Modal } from "../../components/common/Modal";
import {
  EditorPanel,
  PrescriptionInputPanel,
} from "../../components/emr/EditorPanels";
import { ImagePreviewModal } from "../../components/emr/ImagePreviewModal";
import { IntakePanel } from "../../components/emr/IntakePanel";
import {
  EmptyPatientPanel,
  HistoryPanel,
  PatientInfoPanel,
} from "../../components/emr/PatientPanels";
import { PrescriptionPreviewModal } from "../../components/emr/PrescriptionPreviewModal";
import { ProfileEditModal } from "../../components/emr/ProfileEditModal";
import { QueuePanel } from "../../components/emr/QueuePanel";
import { useEmrData } from "../../hooks/useEmrData";
import AppLayout, { AppMenuId } from "../../layouts/AppLayout";
import { createMockPrescriptionDocument } from "./emrMockData";

interface EmrPageProps {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

export default function EmrPage({ session, onLogout, onNavigate }: EmrPageProps) {
  const {
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
    isPrescriptionPreviewOpen,
    isProfileEditOpen,
    previewImage,
    lastRefreshText,
    currentQueue,
    currentEmr,
    visibleGuardianFiles,
    hiddenGuardianFileCount,
    queueTitle,
    handleChangeTab,
    setSelectedScheduleId,
    setEditorValue,
    setIsPrescriptionPreviewOpen,
    setIsProfileEditOpen,
    setPreviewImage,
    handleChangeDate,
    handleMoveDate,
    handleGoToday,
    autoPrescriptionError,
    validationResult,
    followupItems,
    handleRefreshQueue,
    handleCompleteVisit,
    handleApplyIntake,
    handleRemoveFile,
    handleUploadFile,
    handleRemovePrescription,
    handleUpdatePrescription,
    handleGeneratePrescription,
    handleAddPrescription,
    handleResetToWaiting,
    openPreviewImage,
    handlePetInfoSaved,
  } = useEmrData();

  const location = useLocation();
  const targetScheduleId = (location.state as { scheduleId?: number } | null)?.scheduleId;
  useEffect(() => {
    if (!targetScheduleId) return;
    const combined = [...waitingQueue, ...completedQueue];
    if (combined.some((p) => p.schedule_id === targetScheduleId)) {
      setSelectedScheduleId(targetScheduleId);
    }
  }, [targetScheduleId, waitingQueue, completedQueue, setSelectedScheduleId]);
  const [prescriptionPreviewError, setPrescriptionPreviewError] = useState<string | null>(null);
  const [prescriptionPreviewDocument, setPrescriptionPreviewDocument] =
    useState<ReturnType<typeof createMockPrescriptionDocument> | null>(null);
  const [isCompleteConfirmOpen, setIsCompleteConfirmOpen] = useState(false);
  const [alertBannerMessage, setAlertBannerMessage] = useState<string | null>(null);
  const isReadOnly = !isTodayView || queueTab === "completed";
  const showEditablePanels = isTodayView;
  const readOnlyMessage = !isTodayView
    ? "조회 전용 날짜입니다. 기록 수정은 오늘 진료에서만 가능합니다."
    : queueTab === "completed"
      ? "진료 완료 기록입니다. 수정하려면 진료 대기로 되돌려야 합니다."
      : null;
  const alertMessage = completeVisitError ?? autoPrescriptionError;

  useEffect(() => {
    if (prescriptions.length > 0) {
      setPrescriptionPreviewError(null);
    }
  }, [prescriptions.length]);

  useEffect(() => {
    setPrescriptionPreviewError(null);
    setPrescriptionPreviewDocument(null);
    setIsCompleteConfirmOpen(false);
    setAlertBannerMessage(null);
  }, [selectedScheduleId]);

  useEffect(() => {
    if (alertMessage) {
      setAlertBannerMessage(alertMessage);
    }
  }, [alertMessage]);

  useEffect(() => {
    if (!alertBannerMessage) return;

    const timer = window.setTimeout(() => {
      setAlertBannerMessage(null);
    }, 3000);

    return () => window.clearTimeout(timer);
  }, [alertBannerMessage]);

  useEffect(() => {
    if (!prescriptionPreviewError) return;

    const timer = window.setTimeout(() => {
      setPrescriptionPreviewError(null);
    }, 3000);

    return () => window.clearTimeout(timer);
  }, [prescriptionPreviewError]);

  const handleOpenPrescriptionPreview = () => {
    setAlertBannerMessage(null);
    setPrescriptionPreviewError(null);

    if (!currentEmr) {
      const message = "환자 정보를 불러온 뒤 다시 시도해주세요.";
      setPrescriptionPreviewError(message);
      return;
    }

    if (prescriptions.length === 0) {
      const message = "미리보기할 처방전 초안이 없습니다.";
      setPrescriptionPreviewError(message);
      return;
    }

    try {
      const allQueue = [...waitingQueue, ...completedQueue].sort((a, b) =>
        a.time.localeCompare(b.time)
      );
      const selectedPatient = allQueue.find(
        (q) => q.schedule_id === selectedScheduleId
      );
      const queuePosition =
        allQueue.findIndex((q) => q.schedule_id === selectedScheduleId) + 1 || 1;

      setPrescriptionPreviewDocument(
        createMockPrescriptionDocument({
          pet: currentEmr.pet_info,
          prescriptions,
          doctorName: session.user.name,
          hospitalName: session.user.hospitalName,
          ownerName: selectedPatient?.guardian_name ?? "",
          queuePosition,
        })
      );
      setIsPrescriptionPreviewOpen(true);
    } catch (err) {
      console.error("[PrescriptionPreview] open failed:", err);
      const message = "미리보기할 처방전 초안이 없습니다.";
      setPrescriptionPreviewError(message);
    }
  };

  const handleConfirmCompleteVisit = async () => {
    setIsCompleteConfirmOpen(false);
    setAlertBannerMessage(null);
    await handleCompleteVisit();
  };

  const handleGeneratePrescriptionClick = () => {
    setAlertBannerMessage(null);
    handleGeneratePrescription();
  };

  return (
    <AppLayout
      session={session}
      activeMenu="emr"
      serviceName="동물병원 의료 보조 시스템"
      notificationCount={3}
      onLogout={onLogout}
      onNavigate={onNavigate}
      compact
    >
      <div className="relative h-full min-h-0 overflow-hidden text-[12px]">
        {alertBannerMessage && (
          <div className="absolute left-1/2 top-2 z-20 w-[min(720px,calc(100%-32px))] -translate-x-1/2">
            <EmrAlertBanner message={alertBannerMessage} />
          </div>
        )}

        <ResizableGroup
          orientation="horizontal"
          className="h-full min-h-0 overflow-hidden rounded-md border border-[#cfd8e6] bg-[#dbe3ee]"
        >
          <ResizablePanel
            defaultSize="22%"
            minSize="16%"
            maxSize="32%"
            className="min-w-0"
          >
            <WorkspacePane title="접수 / 대기" meta={`${currentQueue.length}명`}>
              <div className="flex h-full min-h-0 flex-col gap-1.5">
                <div className="min-h-[240px] flex-[1.15] overflow-hidden">
                  <QueuePanel
                    title={queueTitle}
                    activeTab={queueTab}
                    queue={currentQueue}
                    selectedScheduleId={selectedScheduleId}
                    lastRefreshText={lastRefreshText}
                    waitingCount={waitingQueue.length}
                    completedCount={completedQueue.length}
                    selectedDate={selectedDate}
                    isTodayView={isTodayView}
                    onChangeTab={handleChangeTab}
                    onSelectPatient={setSelectedScheduleId}
                    onRefresh={handleRefreshQueue}
                    onChangeDate={handleChangeDate}
                    onMoveDate={handleMoveDate}
                    onGoToday={handleGoToday}
                  />
                </div>

                {currentEmr ? (
                  <div className="min-h-[220px] flex-1 overflow-hidden">
                    <PatientInfoPanel
                      patient={currentEmr.pet_info}
                      onEdit={() => {
                        if (isTodayView) setIsProfileEditOpen(true);
                      }}
                      isReadOnly={isReadOnly}
                    />
                  </div>
                ) : (
                  <CompactNotice title="환자 정보" message="환자를 선택하면 기본 정보가 표시됩니다." />
                )}

                {currentEmr &&
                  validationResult &&
                  validationResult.overall !== "OK" &&
                  Array.isArray(validationResult.checks) && (
                    <ValidationNotice
                      checks={validationResult.checks as Array<{ item: string; status: string; detail: string }>}
                    />
                  )}
              </div>
            </WorkspacePane>
          </ResizablePanel>

          <SplitHandle />

          <ResizablePanel
            defaultSize={showEditablePanels ? "28%" : "78%"}
            minSize={showEditablePanels ? "20%" : "50%"}
            maxSize={showEditablePanels ? "38%" : "84%"}
            className="min-w-0"
          >
            <WorkspacePane title="사전 문진 / 히스토리" meta={currentEmr?.pet_info.pet_name ?? "미선택"}>
              <div className="space-y-1.5">
                {currentEmr ? (
                  <>
                    <IntakePanel
                      emr={currentEmr}
                      visibleFiles={visibleGuardianFiles}
                      hiddenFileCount={hiddenGuardianFileCount}
                      onApplyIntake={handleApplyIntake}
                      onPreviewImage={openPreviewImage}
                      isReadOnly={isReadOnly}
                    />
                    {readOnlyMessage && <ReadOnlyBadge message={readOnlyMessage} />}
                    <HistoryPanel histories={currentEmr.emr_history} />
                    {followupItems.length > 0 && <FollowupPanel items={followupItems} />}
                    {isTodayView && queueTab === "completed" && (
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={handleResetToWaiting}
                          className="h-8 rounded-md border border-[#dfe6f1] bg-white px-3 text-xs font-extrabold text-[#59657a] hover:border-[#357b70] hover:text-[#2f6f67]"
                        >
                          진료 대기로 되돌리기
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <EmptyPatientPanel />
                )}
              </div>
            </WorkspacePane>
          </ResizablePanel>

          {showEditablePanels && (
            <>
              <SplitHandle />

              <ResizablePanel defaultSize="50%" minSize="36%" maxSize="64%" className="min-w-0">
                <WorkspacePane title="진료 / 첨부 / 처방" meta={isReadOnly ? "조회 전용" : "작성 가능"}>
                  <div className="grid gap-1.5">
                    <EditorPanel
                      value={editorValue}
                      onChange={setEditorValue}
                      onCompleteVisit={() => setIsCompleteConfirmOpen(true)}
                      files={uploadedFiles}
                      onUploadFile={handleUploadFile}
                      onRemoveFile={handleRemoveFile}
                      onPreviewImage={openPreviewImage}
                      errorMessage={completeVisitError}
                      isUploading={isUploadingFile}
                      uploadError={uploadError}
                      isReadOnly={isReadOnly}
                    />
                    <PrescriptionInputPanel
                      prescriptions={prescriptions}
                      onRemove={handleRemovePrescription}
                      onUpdate={handleUpdatePrescription}
                      onAdd={handleAddPrescription}
                      onGenerate={handleGeneratePrescriptionClick}
                      accessToken={session.accessToken}
                      errorMessage={autoPrescriptionError}
                      onOpenPreview={handleOpenPrescriptionPreview}
                      previewErrorMessage={prescriptionPreviewError}
                      isReadOnly={isReadOnly}
                      isGenerating={isLoadingAutoPresc}
                    />
                  </div>
                </WorkspacePane>
              </ResizablePanel>
            </>
          )}

          {!showEditablePanels && (
            <>
              <SplitHandle hidden />
              <ResizablePanel
                defaultSize="0%"
                minSize="0%"
                maxSize="0%"
                disabled
                className="min-w-0 overflow-hidden"
              />
            </>
          )}
        </ResizableGroup>

        {currentEmr && isProfileEditOpen && isTodayView && (
          <ProfileEditModal
            patient={currentEmr.pet_info}
            onClose={() => setIsProfileEditOpen(false)}
            onSaved={handlePetInfoSaved}
          />
        )}

        {currentEmr && isCompleteConfirmOpen && (
          <Modal
            title="진료를 완료하시겠습니까?"
            onClose={() => setIsCompleteConfirmOpen(false)}
            maxWidthClassName="max-w-[520px]"
            footer={
              <>
                <Button variant="secondary" onClick={() => setIsCompleteConfirmOpen(false)}>
                  취소
                </Button>
                <Button variant="primary" onClick={handleConfirmCompleteVisit}>
                  진료 완료
                </Button>
              </>
            }
          >
            <div className="space-y-4">
              <div className="rounded-lg bg-[#f8fafc] px-4 py-3">
                <p className="text-sm font-extrabold text-[#151b28]">
                  {currentEmr.pet_info.pet_name}의 오늘 진료를 완료 처리합니다.
                </p>
                <p className="mt-1 text-xs font-bold text-[#697386]">
                  완료 후 환자는 진료 완료 탭으로 이동합니다.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg border border-[#e8edf4] px-4 py-3">
                  <p className="text-xs font-bold text-[#8a94a6]">처방 항목</p>
                  <p className="mt-1 text-lg font-extrabold text-[#151b28]">
                    {prescriptions.length}개
                  </p>
                </div>
                <div className="rounded-lg border border-[#e8edf4] px-4 py-3">
                  <p className="text-xs font-bold text-[#8a94a6]">첨부 파일</p>
                  <p className="mt-1 text-lg font-extrabold text-[#151b28]">
                    {uploadedFiles.length}개
                  </p>
                </div>
              </div>
              <p className="text-xs font-bold leading-5 text-[#8a94a6]">
                처방전과 첨부 파일은 현재 입력된 내용 기준으로 함께 저장됩니다.
              </p>
            </div>
          </Modal>
        )}

        {previewImage && (
          <ImagePreviewModal
            image={previewImage}
            onClose={() => setPreviewImage(null)}
          />
        )}

        {prescriptionPreviewDocument && isPrescriptionPreviewOpen && (
          <PrescriptionPreviewModal
            document={prescriptionPreviewDocument}
            onClose={() => {
              setIsPrescriptionPreviewOpen(false);
              setPrescriptionPreviewDocument(null);
            }}
          />
        )}
      </div>
    </AppLayout>
  );
}

function WorkspacePane({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-[#f5f7fb]">
      <div className="flex h-8 shrink-0 items-center justify-between border-b border-[#cfd8e6] bg-[#eaf0f7] px-2.5">
        <h2 className="truncate text-[12px] font-extrabold text-[#1f2937]">{title}</h2>
        {meta && (
          <span className="ml-2 shrink-0 rounded bg-white/70 px-1.5 py-0.5 text-[10px] font-extrabold text-[#64748b]">
            {meta}
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1.5">
        {children}
      </div>
    </section>
  );
}

function SplitHandle({ hidden = false }: { hidden?: boolean }) {
  return (
    <ResizeSeparator
      disabled={hidden}
      className={[
        "group relative w-1 shrink-0 outline-none transition",
        hidden
          ? "pointer-events-none bg-transparent"
          : "bg-[#c7d2e1] hover:bg-[#7aa7cc] focus-visible:bg-[#3b82f6] data-[resize-handle-active]:bg-[#3b82f6]",
      ].join(" ")}
    >
      {!hidden && (
        <span className="absolute left-1/2 top-1/2 h-10 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/70 opacity-0 transition group-hover:opacity-100" />
      )}
    </ResizeSeparator>
  );
}

function CompactNotice({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-[#e1e8f2] bg-white px-3 py-4 text-center shadow-sm">
      <p className="text-xs font-extrabold text-[#20283a]">{title}</p>
      <p className="mt-1 text-[11px] font-bold leading-4 text-[#8a94a6]">{message}</p>
    </div>
  );
}

function ValidationNotice({
  checks,
}: {
  checks: Array<{ item: string; status: string; detail: string }>;
}) {
  const visibleChecks = checks.filter((c) => c.status !== "PASS" && c.status !== "SKIPPED");

  if (visibleChecks.length === 0) return null;

  return (
    <div className="shrink-0 rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-2 text-xs text-yellow-800">
      <div className="flex items-center gap-1.5 font-bold">
        <TriangleAlert className="h-3.5 w-3.5" strokeWidth={2.2} />
        <span>검토 권고</span>
      </div>
      <ul className="mt-1.5 space-y-1 leading-snug text-yellow-900/90">
        {visibleChecks.map((c) => (
          <li key={c.item}>
            <span className="font-bold">{c.item}</span> - {c.detail}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FollowupPanel({ items }: { items: FollowupItem[] }) {
  return (
    <div className="rounded-lg border border-[#e8edf4] bg-white p-3 shadow-sm">
      <h3 className="mb-2 text-xs font-extrabold text-[#151b28]">경과 보고</h3>
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.followup_id}
            className={`border-l-2 py-1 pl-3 ${
              item.emergency_alert ? "border-[#ef4444]" : "border-[#cbd5e1]"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] text-[#a8b0bf]">
                {item.created_at
                  ? new Date(item.created_at).toLocaleString("ko-KR", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : ""}
              </p>
              {item.emergency_alert && (
                <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-extrabold text-[#ef4444]">
                  <TriangleAlert className="h-3 w-3" strokeWidth={2.2} />
                  응급 신호
                </span>
              )}
            </div>
            <p className="mt-1 text-xs font-bold leading-relaxed text-[#151b28]">
              {item.ai_summary ?? "경과 요약을 생성 중입니다."}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReadOnlyBadge({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-[#dfe6f1] bg-[#f8fafc] px-4 py-3 text-sm font-extrabold text-[#59657a]">
      <TriangleAlert className="h-4 w-4 text-[#64748b]" strokeWidth={2.2} />
      {message}
    </div>
  );
}

function EmrAlertBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-700 shadow-sm">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2.2} />
        <span>{message}</span>
      </div>
    </div>
  );
}
