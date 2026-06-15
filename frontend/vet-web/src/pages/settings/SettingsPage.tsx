import { useState } from "react";
import { CalendarX, Clock3, LockKeyhole, Users } from "lucide-react";
import type { AuthSession } from "../../api/authApi";
import AppLayout, { AppMenuId } from "../../layouts/AppLayout";
import { HospitalHoursModal } from "../../components/settings/HospitalHoursModal";
import { ClosedDatesModal } from "../../components/settings/ClosedDatesModal";
import { VetScheduleModal } from "../../components/settings/VetScheduleModal";
import { VetScheduleDetailModal } from "../../components/settings/VetScheduleDetailModal";
import { PasswordChangeModal } from "../../components/settings/PasswordChangeModal";

interface SettingsPageProps {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

type ModalType =
  | "hospital-hours"
  | "closed-dates"
  | "vet-schedule"
  | "vet-detail"
  | "password"
  | null;

export default function SettingsPage({ session, onLogout, onNavigate }: SettingsPageProps) {
  const [activeModal, setActiveModal] = useState<ModalType>(null);
  const [detailInitialVetId, setDetailInitialVetId] = useState<number | undefined>();

  const openVetDetail = (vetId?: number) => {
    setDetailInitialVetId(vetId);
    setActiveModal("vet-detail");
  };

  const close = () => setActiveModal(null);

  return (
    <AppLayout session={session} activeMenu="settings" onLogout={onLogout} onNavigate={onNavigate}>
      {activeModal === "hospital-hours" && (
        <HospitalHoursModal session={session} onClose={close} />
      )}
      {activeModal === "closed-dates" && (
        <ClosedDatesModal session={session} onClose={close} />
      )}
      {activeModal === "vet-schedule" && (
        <VetScheduleModal session={session} onClose={close} onOpenDetail={openVetDetail} />
      )}
      {activeModal === "vet-detail" && (
        <VetScheduleDetailModal
          session={session}
          initialVetId={detailInitialVetId}
          onClose={close}
        />
      )}
      {activeModal === "password" && (
        <PasswordChangeModal session={session} onClose={close} />
      )}

      <div className="flex flex-col h-full">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold text-slate-900">설정</h1>
          <p className="mt-1 text-sm font-bold text-slate-500">
            병원 운영 환경 및 계정 보안을 관리합니다.
          </p>
        </div>

        <div className="space-y-4 max-w-2xl">
          {/* 병원 운영 */}
          <SettingSection title="병원 운영" description="병원 운영 시간과 휴진 일정을 관리합니다.">
            <SettingRow
              icon={<Clock3 className="h-5 w-5 text-blue-600" strokeWidth={2.2} />}
              title="병원 운영 시간"
              description="요일별 기본 운영 시간과 점심 시간을 설정합니다."
              onAction={() => setActiveModal("hospital-hours")}
            />
            <SettingRow
              icon={<CalendarX className="h-5 w-5 text-blue-600" strokeWidth={2.2} />}
              title="특정일 휴진"
              description="공휴일, 대체휴일 등 특정 날짜의 휴진을 관리합니다."
              onAction={() => setActiveModal("closed-dates")}
              noBorder
            />
          </SettingSection>

          {/* 구성원 근무 */}
          <SettingSection title="구성원 근무" description="수의사별 근무 시간을 설정합니다.">
            <SettingRow
              icon={<Users className="h-5 w-5 text-blue-600" strokeWidth={2.2} />}
              title="의사별 근무 시간"
              description="수의사별 출퇴근, 퇴근, 점심 시간을 설정합니다."
              onAction={() => setActiveModal("vet-schedule")}
              noBorder
            />
          </SettingSection>

          {/* 계정 및 보안 */}
          <SettingSection title="계정 및 보안" description="계정 정보 및 보안을 관리합니다.">
            <SettingRow
              icon={<LockKeyhole className="h-5 w-5 text-blue-600" strokeWidth={2.2} />}
              title="관리자 비밀번호 변경"
              description="비밀번호를 변경해주세요."
              buttonLabel="비밀번호 변경"
              onAction={() => setActiveModal("password")}
              noBorder
            />
          </SettingSection>
        </div>
      </div>
    </AppLayout>
  );
}

// ── 레이아웃 컴포넌트 ─────────────────────────────────────────────────

function SettingSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4">
        <h2 className="text-base font-extrabold text-slate-900">{title}</h2>
        <p className="mt-0.5 text-xs font-semibold text-slate-400">{description}</p>
      </div>
      <div>{children}</div>
    </section>
  );
}

function SettingRow({
  icon,
  title,
  description,
  buttonLabel = "설정",
  onAction,
  noBorder = false,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  buttonLabel?: string;
  onAction: () => void;
  noBorder?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-4 px-5 py-4 ${!noBorder ? "border-b border-slate-100" : ""}`}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-extrabold text-slate-800">{title}</p>
        <p className="mt-0.5 text-xs font-semibold text-slate-400">{description}</p>
      </div>
      <button
        type="button"
        onClick={onAction}
        className="h-9 shrink-0 whitespace-nowrap rounded-lg border border-blue-200 bg-white px-4 text-sm font-extrabold text-blue-600 transition hover:bg-blue-50"
      >
        {buttonLabel}
      </button>
    </div>
  );
}
