import { AuthSession } from "../../api/authApi";
import { AutoPrescriptionPanel } from "../../components/emr/AutoPrescriptionPanel";
import {
  EditorPanel,
  PhotoUploadPanel,
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
    queueTab,
    waitingQueue,
    completedQueue,
    selectedScheduleId,
    editorValue,
    uploadedFiles,
    isUploadingFile,
    uploadError,
    prescriptions,
    isPrescriptionPreviewOpen,
    isProfileEditOpen,
    previewImage,
    lastRefreshText,
    currentQueue,
    currentEmr,
    visibleGuardianFiles,
    hiddenGuardianFileCount,
    queueTitle,
    setQueueTab,
    setSelectedScheduleId,
    setEditorValue,
    setIsPrescriptionPreviewOpen,
    setIsProfileEditOpen,
    setPreviewImage,
    autoPrescriptions,
    isLoadingAutoPresc,
    validationResult,
    followupItems,
    handleRefreshQueue,
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
    openPreviewImage,
  } = useEmrData();
  const isReadOnly = queueTab === "completed";

  return (
    <AppLayout
      session={session}
      activeMenu="emr"
      serviceName="동물병원 의료 보조 시스템"
      notificationCount={3}
      onLogout={onLogout}
      onNavigate={onNavigate}
    >
      <div className="min-h-[calc(100vh-72px)] bg-[#f6f8fb] p-4">
        <div className="grid grid-cols-[300px_minmax(620px,1fr)_320px] gap-4">
          <aside className="sticky top-[88px] grid h-[calc(100vh-104px)] grid-rows-[320px_minmax(0,1fr)] gap-3 overflow-hidden">
            <QueuePanel
              title={queueTitle}
              activeTab={queueTab}
              queue={currentQueue}
              selectedScheduleId={selectedScheduleId}
              lastRefreshText={lastRefreshText}
              waitingCount={waitingQueue.length}
              completedCount={completedQueue.length}
              onChangeTab={setQueueTab}
              onSelectPatient={setSelectedScheduleId}
              onRefresh={handleRefreshQueue}
            />

            {currentEmr && (
              <IntakePanel
                emr={currentEmr}
                visibleFiles={visibleGuardianFiles}
                hiddenFileCount={hiddenGuardianFileCount}
                onApplyIntake={handleApplyIntake}
                onPreviewImage={openPreviewImage}
                isReadOnly={isReadOnly}
              />
            )}

            {/* AI 사전문진 검증 — '예외'만 표시(정상 항목은 숨김). 응급도/증상은 위에서 이미 봤으므로
                여기엔 문진만 봐선 모를 것(누락·문진↔차트 불일치·응급도 불일치)만 가볍게 띄운다. */}
            {currentEmr &&
              validationResult &&
              validationResult.overall !== "OK" &&
              Array.isArray(validationResult.checks) && (
                <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-2.5 text-xs text-yellow-800">
                  <div className="flex items-center gap-1.5 font-bold">
                    <span aria-hidden>⚠️</span>
                    <span>검토 권고</span>
                  </div>
                  <ul className="mt-1.5 space-y-1 leading-snug text-yellow-900/90">
                    {(validationResult.checks as Array<{ item: string; status: string; detail: string }>)
                      .filter((c) => c.status !== "PASS" && c.status !== "SKIPPED")
                      .map((c) => (
                        <li key={c.item}>
                          <span className="font-bold">{c.item}</span> — {c.detail}
                        </li>
                      ))}
                  </ul>
                </div>
              )}
          </aside>

          <main className="space-y-4">
            {currentEmr ? (
              <>
                <PatientInfoPanel
                  patient={currentEmr.pet_info}
                  onEdit={() => setIsProfileEditOpen(true)}
                  isReadOnly={isReadOnly}
                />
                <HistoryPanel histories={currentEmr.emr_history} />
                {followupItems.length > 0 && (
                  <div className="rounded-xl border border-[#e8edf4] bg-white p-5 shadow-sm">
                    <h3 className="mb-3 text-sm font-extrabold text-[#151b28]">경과 보고</h3>
                    <div className="space-y-3">
                      {followupItems.map((item) => (
                        <div key={item.followup_id} className={`border-l-2 pl-3 ${item.emergency_alert ? 'border-red-500 bg-red-50/50 pr-2 py-1' : 'border-[#4a89ff]'}`}>
                          <div className="flex items-center justify-between">
                            <p className="text-xs text-[#a8b0bf]">
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
                              <span className="text-[10px] font-black text-red-600 bg-red-100 px-1.5 py-0.5 rounded">
                                🚨 응급 신호 감지
                              </span>
                            )}
                          </div>
                          <p className="mt-0.5 text-sm text-[#151b28]">
                            {item.message ?? "(내용 없음)"}
                          </p>
                          {item.ai_summary && (
                            <div className="mt-1 bg-slate-50 p-2 rounded text-xs text-[#4e5968] border border-slate-100">
                              <span className="font-extrabold text-blue-600">AI 요약:</span> {item.ai_summary}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <EmptyPatientPanel />
            )}
            <EditorPanel
              value={editorValue}
              count={editorValue.length}
              onChange={setEditorValue}
              onCompleteVisit={handleCompleteVisit}
              isReadOnly={isReadOnly}
            />
            <PhotoUploadPanel
              files={uploadedFiles}
              onUploadFile={handleUploadFile}
              onRemoveFile={handleRemoveFile}
              onPreviewImage={openPreviewImage}
              isUploading={isUploadingFile}
              uploadError={uploadError}
              isReadOnly={isReadOnly}
            />
            <PrescriptionInputPanel
              prescriptions={prescriptions}
              onRemove={handleRemovePrescription}
              onUpdate={handleUpdatePrescription}
              onSave={handleSavePrescription}
              onAdd={handleAddPrescription}
              onGenerate={handleGeneratePrescription}
              accessToken={session.accessToken}
              isReadOnly={isReadOnly}
            />
          </main>

          <AutoPrescriptionPanel
            patient={currentEmr?.pet_info}
            prescriptions={autoPrescriptions}
            isLoading={isLoadingAutoPresc}
            onClose={handleClearAutoPrescription}
            onLoad={handleLoadAutoPrescription}
            onApply={handleApplyAutoPrescription}
            onOpenPreview={() => setIsPrescriptionPreviewOpen(true)}
            isReadOnly={isReadOnly}
          />
        </div>

        {currentEmr && isProfileEditOpen && (
          <ProfileEditModal
            patient={currentEmr.pet_info}
            onClose={() => setIsProfileEditOpen(false)}
          />
        )}

        {previewImage && (
          <ImagePreviewModal
            image={previewImage}
            onClose={() => setPreviewImage(null)}
          />
        )}

        {currentEmr && isPrescriptionPreviewOpen && (
          <PrescriptionPreviewModal
            document={createMockPrescriptionDocument({
              pet: currentEmr.pet_info,
              prescriptions: autoPrescriptions,
            })}
            onClose={() => setIsPrescriptionPreviewOpen(false)}
          />
        )}
      </div>
    </AppLayout>
  );
}
