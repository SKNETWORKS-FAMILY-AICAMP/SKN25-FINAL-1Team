import { useState } from "react";
import { LockKeyhole } from "lucide-react";
import type { AuthSession } from "../../api/authApi";
import AppLayout, { AppMenuId } from "../../layouts/AppLayout";
import { PasswordChangeModal } from "../../components/settings/PasswordChangeModal";
import { startVetProductTour } from "../../components/ProductTour";

interface SettingsPageProps {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

type ModalType = "password" | null;

export default function SettingsPage({ session, onLogout, onNavigate }: SettingsPageProps) {
  const [activeModal, setActiveModal] = useState<ModalType>(null);

  const close = () => setActiveModal(null);

  return (
    <AppLayout session={session} activeMenu="settings" onLogout={onLogout} onNavigate={onNavigate}>
      {activeModal === "password" && (
        <PasswordChangeModal session={session} onClose={close} />
      )}

      <div className="flex flex-col h-full">
        <div className="mb-6 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold text-slate-900">설정</h1>
            <p className="mt-1 text-sm font-bold text-slate-500">
              계정 보안을 관리합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={startVetProductTour}
            className="h-9 shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-xs font-extrabold text-slate-600 transition hover:border-blue-200 hover:text-blue-600"
          >
            튜토리얼 다시보기
          </button>
        </div>

        <div data-tour="vet-settings" className="space-y-4 max-w-2xl">
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
