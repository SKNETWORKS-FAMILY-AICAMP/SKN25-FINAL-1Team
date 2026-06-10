import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CalendarX,
  CheckCircle2,
  Clock3,
  LockKeyhole,
  Plus,
  Save,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  AuthSession,
  changePassword,
  isPasswordPolicyValid,
  getPasswordPolicyStatus,
} from "../../api/authApi";
import {
  type DaySchedule,
  fetchWeeklySchedule,
  updateWeeklySchedule,
  fetchClosedDates,
  addClosedDate,
  removeClosedDate,
} from "../../api/settingsApi";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";
import AppLayout, { AppMenuId } from "../../layouts/AppLayout";

interface SettingsPageProps {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

const DAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

const timeOptions = [
  "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
  "11:00", "11:30", "12:00", "12:30", "13:00", "13:30",
  "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
  "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
  "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00",
];

const defaultWeek: DaySchedule[] = Array.from({ length: 7 }, (_, i) => ({
  day_of_week: i,
  is_open: i < 5,
  start_time: i < 5 ? "09:00" : null,
  end_time: i < 5 ? "18:00" : null,
  lunch_start: i < 5 ? "12:00" : null,
  lunch_end: i < 5 ? "13:00" : null,
}));

export default function SettingsPage({
  session,
  onLogout,
  onNavigate,
}: SettingsPageProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  // 주간 스케줄
  const [weekSchedule, setWeekSchedule] = useState<DaySchedule[]>(defaultWeek);
  const [isWeeklySaved, setIsWeeklySaved] = useState(false);
  const [weeklyError, setWeeklyError] = useState("");

  // 일괄 적용
  const [bulkTimes, setBulkTimes] = useState({
    start_time: "09:00",
    end_time: "18:00",
    lunch_start: "12:00",
    lunch_end: "13:00",
  });

  // 특정일 휴진
  const [closedDates, setClosedDates] = useState<string[]>([]);
  const [newClosedDate, setNewClosedDate] = useState("");
  const [closedDateSuccess, setClosedDateSuccess] = useState("");
  const [closedDateWarning, setClosedDateWarning] = useState("");
  const [closedDateError, setClosedDateError] = useState("");

  useEffect(() => {
    fetchWeeklySchedule(session.accessToken)
      .then(setWeekSchedule)
      .catch(() => {});
    fetchClosedDates(session.accessToken)
      .then(setClosedDates)
      .catch(() => {});
  }, [session.accessToken]);

  const updateDay = (dow: number, patch: Partial<DaySchedule>) => {
    setWeekSchedule((prev) =>
      prev.map((d) => (d.day_of_week === dow ? { ...d, ...patch } : d))
    );
    setIsWeeklySaved(false);
    setWeeklyError("");
  };

  const toggleOpen = (dow: number) => {
    const day = weekSchedule.find((d) => d.day_of_week === dow)!;
    if (!day.is_open) {
      updateDay(dow, {
        is_open: true,
        start_time: "09:00",
        end_time: "18:00",
        lunch_start: "12:00",
        lunch_end: "13:00",
      });
    } else {
      updateDay(dow, {
        is_open: false,
        start_time: null,
        end_time: null,
        lunch_start: null,
        lunch_end: null,
      });
    }
  };

  const applyBulkTimes = () => {
    setWeekSchedule((prev) =>
      prev.map((d) =>
        d.is_open
          ? { ...d, ...bulkTimes }
          : d
      )
    );
    setIsWeeklySaved(false);
    setWeeklyError("");
  };

  const handleSaveWeekly = async () => {
    try {
      const saved = await updateWeeklySchedule(session.accessToken, weekSchedule);
      setWeekSchedule(saved);
      setIsWeeklySaved(true);
      setWeeklyError("");
    } catch {
      setWeeklyError("저장에 실패했습니다.");
    }
  };

  const handleAddClosedDate = async () => {
    if (!newClosedDate) return;
    setClosedDateSuccess("");
    setClosedDateWarning("");
    setClosedDateError("");
    try {
      const result = await addClosedDate(session.accessToken, newClosedDate);
      setClosedDates((prev) => [...prev, newClosedDate].sort());
      setNewClosedDate("");
      if (result.has_existing_reservations) {
        setClosedDateWarning(
          `해당 날짜에 예약이 ${result.reservation_count}건 있습니다. 기존 예약은 자동으로 취소되지 않으니 직접 처리해주세요.`
        );
      } else {
        setClosedDateSuccess("휴진일이 등록되었습니다.");
      }
    } catch {
      setClosedDateError("휴진일 등록에 실패했습니다.");
    }
  };

  const handleRemoveClosedDate = async (d: string) => {
    setClosedDateSuccess("");
    setClosedDateWarning("");
    setClosedDateError("");
    try {
      await removeClosedDate(session.accessToken, d);
      setClosedDates((prev) => prev.filter((x) => x !== d));
      setClosedDateSuccess("휴진일이 해제되었습니다.");
    } catch {
      setClosedDateError("휴진일 해제에 실패했습니다.");
    }
  };

  return (
    <AppLayout
      session={session}
      activeMenu="settings"
      onLogout={onLogout}
      onNavigate={onNavigate}
    >
      {isModalOpen && (
        <PasswordChangeModal
          session={session}
          onClose={() => setIsModalOpen(false)}
        />
      )}

      <div className="flex min-w-0 flex-col h-full">
        <div className="mb-4 flex min-w-0 flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-extrabold text-[#151b28]">설정</h1>
            <p className="mt-2 text-sm font-bold text-[#65718a]">
              병원 운영 환경 및 계정 보안을 관리합니다.
            </p>
          </div>
        </div>

        <div className="grid w-full flex-1 grid-cols-2 grid-rows-1 gap-4">

          {/* ── 왼쪽: 요일별 운영 시간 + 특정일 휴진 ── */}
          <div className="flex flex-col gap-4">

            {/* 요일별 운영 시간 */}
            <section className="rounded-lg border border-[#e5eaf2] bg-white shadow-sm">
              <div className="flex items-center gap-2 border-b border-[#e5eaf2] bg-[#eef5f4] px-4 py-2.5">
                <Clock3 className="h-4 w-4 shrink-0 text-[#2f6f67]" strokeWidth={2.2} />
                <h2 className="text-sm font-extrabold text-[#151b28]">요일별 운영 시간</h2>
              </div>
              <div className="px-4 py-2.5 space-y-0.5">
                <div className="flex items-center gap-3 rounded-lg px-3 py-2 mb-0.5 border-b border-[#e5eaf2]">
                  <span className="w-[6.25rem] shrink-0 text-xs font-extrabold text-[#2f6f67]">일괄 적용</span>
                  <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                    <InlineTimeSelect value={bulkTimes.start_time} onChange={(v) => setBulkTimes((p) => ({ ...p, start_time: v }))} />
                    <span className="text-xs text-[#8595ae]">~</span>
                    <InlineTimeSelect value={bulkTimes.end_time} onChange={(v) => setBulkTimes((p) => ({ ...p, end_time: v }))} />
                    <span className="mx-1 text-xs text-[#c5cfe0]">|</span>
                    <span className="text-xs font-bold text-[#8595ae]">점심</span>
                    <InlineTimeSelect value={bulkTimes.lunch_start} onChange={(v) => setBulkTimes((p) => ({ ...p, lunch_start: v }))} />
                    <span className="text-xs text-[#8595ae]">~</span>
                    <InlineTimeSelect value={bulkTimes.lunch_end} onChange={(v) => setBulkTimes((p) => ({ ...p, lunch_end: v }))} />
                  </div>
                  <button
                    type="button"
                    onClick={applyBulkTimes}
                    className="h-7 shrink-0 rounded-lg bg-[#2f6f67] px-2.5 text-xs font-extrabold text-white transition hover:bg-[#255e57]"
                  >
                    전체 적용
                  </button>
                </div>
                {weekSchedule.map((day) => (
                  <DayRow
                    key={day.day_of_week}
                    day={day}
                    label={DAY_LABELS[day.day_of_week]}
                    onToggle={() => toggleOpen(day.day_of_week)}
                    onUpdate={(patch) => updateDay(day.day_of_week, patch)}
                  />
                ))}
                <div className="flex items-center justify-end gap-3 pt-1">
                  {isWeeklySaved && (
                    <p className="text-xs font-extrabold text-[#2f6f67]">저장되었습니다.</p>
                  )}
                  {weeklyError && (
                    <p className="text-xs font-extrabold text-[#dc2626]">{weeklyError}</p>
                  )}
                  <button
                    type="button"
                    onClick={handleSaveWeekly}
                    className="flex h-8 items-center gap-1.5 rounded-lg bg-[#2f6f67] px-3 text-xs font-extrabold text-white transition hover:bg-[#255e57]"
                  >
                    <Save className="h-3.5 w-3.5" />
                    저장
                  </button>
                </div>
              </div>
            </section>

            {/* 특정일 휴진 */}
            <section className="flex flex-col flex-1 rounded-lg border border-[#e5eaf2] bg-white shadow-sm">
              <div className="flex items-center gap-2 border-b border-[#e5eaf2] bg-[#eef5f4] px-4 py-2.5">
                <CalendarX className="h-4 w-4 text-[#2f6f67]" strokeWidth={2.2} />
                <h2 className="text-sm font-extrabold text-[#151b28]">특정일 휴진</h2>
              </div>
              <div className="flex flex-col flex-1 overflow-hidden px-4 py-3 gap-3">
                <div className="shrink-0 flex items-center gap-2">
                  <input
                    type="date"
                    value={newClosedDate}
                    onChange={(e) => {
                      setNewClosedDate(e.target.value);
                      setClosedDateWarning("");
                      setClosedDateError("");
                    }}
                    className="h-9 rounded-lg border border-[#dfe6f1] bg-white px-3 text-sm font-bold text-[#1d2a57] outline-none transition focus:border-[#7fb1a8] focus:ring-2 focus:ring-[#eef5f4]"
                  />
                  <button
                    type="button"
                    onClick={handleAddClosedDate}
                    disabled={!newClosedDate}
                    className="flex h-9 items-center gap-1.5 rounded-lg bg-[#2f6f67] px-3 text-xs font-extrabold text-white transition hover:bg-[#255e57] disabled:cursor-not-allowed disabled:bg-[#aecfc9]"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    휴진 등록
                  </button>
                </div>
                {closedDateSuccess && (
                  <p className="shrink-0 text-xs font-extrabold text-[#2f6f67]">{closedDateSuccess}</p>
                )}
                {closedDateWarning && (
                  <div className="shrink-0 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                    <p className="text-xs font-bold text-amber-700">{closedDateWarning}</p>
                  </div>
                )}
                {closedDateError && (
                  <p className="shrink-0 text-xs font-extrabold text-[#dc2626]">{closedDateError}</p>
                )}
                {closedDates.length > 0 ? (
                  <ul className="flex-1 overflow-y-auto space-y-1.5">
                    {closedDates.map((d) => (
                      <li key={d} className="flex items-center justify-between rounded-lg bg-[#f7f9fc] px-3 py-2">
                        <span className="text-sm font-bold text-[#1d2a57]">{d}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveClosedDate(d)}
                          className="flex items-center gap-1 text-xs font-bold text-[#8595ae] transition hover:text-[#dc2626]"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          해제
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs font-semibold text-[#b0b9cc]">등록된 휴진일이 없습니다.</p>
                )}
              </div>
            </section>

          </div>

          {/* ── 오른쪽: 계정 및 보안 ── */}
          <section className="self-start rounded-lg border border-[#e5eaf2] bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-[#e5eaf2] bg-[#eef5f4] px-4 py-2.5">
              <LockKeyhole className="h-4 w-4 text-[#2f6f67]" strokeWidth={2.2} />
              <h2 className="text-sm font-extrabold text-[#151b28]">계정 및 보안</h2>
            </div>
            <div className="px-4 py-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-extrabold text-[#1d2a57]">관리자 비밀번호 변경</p>
                  <p className="mt-0.5 text-xs font-semibold text-[#8595ae]">계정 보안을 위해 정기적으로 비밀번호를 변경해주세요.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(true)}
                  className="h-9 rounded-lg border border-[#aecfc9] bg-white px-4 text-sm font-extrabold text-[#2f6f67] transition hover:bg-[#eef5f4] whitespace-nowrap"
                >
                  비밀번호 변경
                </button>
              </div>
            </div>
          </section>

        </div>
      </div>
    </AppLayout>
  );
}

// ── DayRow ──────────────────────────────────────────────────────────────

function DayRow({
  day,
  label,
  onToggle,
  onUpdate,
}: {
  day: DaySchedule;
  label: string;
  onToggle: () => void;
  onUpdate: (patch: Partial<DaySchedule>) => void;
}) {
  return (
    <div className={`flex h-11 items-center gap-3 rounded-lg px-3 ${day.is_open ? "bg-white" : "bg-[#f7f9fc]"}`}>
      <span className="w-6 text-center text-sm font-extrabold text-[#344055]">
        {label}
      </span>

      <select
        value={day.is_open ? "open" : "closed"}
        onChange={(e) => {
          const wantsOpen = e.target.value === "open";
          if (wantsOpen !== day.is_open) onToggle();
        }}
        className={`h-7 w-16 shrink-0 rounded-lg border border-[#dfe6f1] bg-white px-1 text-xs font-extrabold outline-none transition focus:border-[#7fb1a8] focus:ring-2 focus:ring-[#eef5f4] ${
          day.is_open ? "text-[#2f6f67]" : "text-[#8595ae]"
        }`}
      >
        <option value="open">영업</option>
        <option value="closed">휴진</option>
      </select>

      {day.is_open ? (
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <InlineTimeSelect
            value={day.start_time ?? "09:00"}
            onChange={(v) => onUpdate({ start_time: v })}
          />
          <span className="text-xs text-[#8595ae]">~</span>
          <InlineTimeSelect
            value={day.end_time ?? "18:00"}
            onChange={(v) => onUpdate({ end_time: v })}
          />
          <span className="mx-1 text-xs text-[#c5cfe0]">|</span>
          <span className="text-xs font-bold text-[#8595ae]">점심</span>
          <InlineTimeSelect
            value={day.lunch_start ?? "12:00"}
            onChange={(v) => onUpdate({ lunch_start: v })}
          />
          <span className="text-xs text-[#8595ae]">~</span>
          <InlineTimeSelect
            value={day.lunch_end ?? "13:00"}
            onChange={(v) => onUpdate({ lunch_end: v })}
          />
        </div>
      ) : (
        <span className="text-xs font-semibold text-[#b0b9cc]">휴진일</span>
      )}
    </div>
  );
}

function InlineTimeSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 rounded-lg border border-[#dfe6f1] bg-white px-2 text-xs font-extrabold text-[#1d2a57] outline-none transition focus:border-[#7fb1a8] focus:ring-2 focus:ring-[#eef5f4]"
    >
      {timeOptions.map((t) => (
        <option key={t} value={t}>{t}</option>
      ))}
    </select>
  );
}

// ── PasswordChangeModal ─────────────────────────────────────────────────

function PasswordChangeModal({
  session,
  onClose,
}: {
  session: AuthSession;
  onClose: () => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const canSubmit =
    currentPassword.length > 0 &&
    newPassword.length > 0 &&
    confirmPassword.length > 0 &&
    !isLoading;

  const policyStatus = getPasswordPolicyStatus(newPassword, session.user.id);

  const handleClose = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError("");
    onClose();
  };

  useEscapeToClose(handleClose, !isLoading);

  const handleSubmit = async () => {
    setError("");

    if (newPassword !== confirmPassword) {
      setError("새 비밀번호와 확인 비밀번호가 일치하지 않습니다.");
      return;
    }
    if (currentPassword === newPassword) {
      setError("현재 비밀번호와 동일한 비밀번호는 사용할 수 없습니다.");
      return;
    }
    if (!isPasswordPolicyValid(newPassword, session.user.id)) {
      setError("비밀번호 정책을 모두 충족한 뒤 변경을 완료해주세요.");
      return;
    }

    setIsLoading(true);
    try {
      await changePassword({
        accessToken: session.accessToken,
        currentPassword,
        newPassword,
        newPasswordConfirm: confirmPassword,
      });
      setSuccess(true);
      setTimeout(() => onClose(), 1800);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "비밀번호 변경 중 오류가 발생했습니다."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-[480px] rounded-lg bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[#e5eaf2] px-6 py-4">
          <div>
            <h2 className="text-lg font-extrabold text-[#151b28]">비밀번호 변경</h2>
            <p className="mt-0.5 text-xs font-semibold text-[#8595ae]">
              다시 사용하신 비밀번호를 입력해주세요.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#8595ae] transition hover:bg-[#f0f4fa] hover:text-[#344055]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {success ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[#eef5f4]">
                <CheckCircle2 className="h-8 w-8 text-[#2f6f67]" />
              </div>
              <p className="text-base font-extrabold text-[#1d2a57]">비밀번호가 변경되었습니다.</p>
              <p className="text-sm font-semibold text-[#8595ae]">잠시 후 자동으로 닫힙니다.</p>
            </div>
          ) : (
            <>
              <PasswordInputField label="현재 비밀번호" value={currentPassword} onChange={setCurrentPassword} placeholder="현재 비밀번호 입력" />
              <PasswordInputField label="새 비밀번호" value={newPassword} onChange={setNewPassword} placeholder="새 비밀번호 입력" />
              <PasswordInputField label="새 비밀번호 확인" value={confirmPassword} onChange={setConfirmPassword} placeholder="새 비밀번호 재입력" />

              {newPassword.length > 0 && (
                <ul className="rounded-lg bg-[#f8fafd] px-4 py-3 space-y-1.5">
                  {policyStatus.map((p) => (
                    <li key={p.label} className="flex items-center gap-2 text-xs font-semibold">
                      <CheckCircle2
                        className={`h-3.5 w-3.5 shrink-0 ${p.isValid ? "text-[#2f6f67]" : "text-[#c5cfe0]"}`}
                      />
                      <span className={p.isValid ? "text-[#4d5874]" : "text-[#b0b9cc]"}>{p.label}</span>
                    </li>
                  ))}
                </ul>
              )}

              {error && (
                <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                  <p className="text-sm font-bold text-red-600">{error}</p>
                </div>
              )}
            </>
          )}
        </div>

        {!success && (
          <div className="flex justify-end gap-3 border-t border-[#e5eaf2] px-6 py-4">
            <button
              type="button"
              onClick={handleClose}
              className="h-10 rounded-lg border border-[#dfe6f1] px-5 text-sm font-extrabold text-[#52607a] transition hover:bg-[#f0f4fa]"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="h-10 rounded-lg bg-[#2f6f67] px-5 text-sm font-extrabold text-white transition hover:bg-[#255e57] disabled:cursor-not-allowed disabled:bg-[#aecfc9]"
            >
              {isLoading ? "변경 중..." : "변경하기"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function PasswordInputField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-extrabold text-[#52607a]">{label}</label>
      <div className="relative">
        <LockKeyhole className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#9aa5b8]" />
        <input
          type="password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-12 w-full rounded-lg border border-[#dfe6f1] bg-white pl-10 pr-4 text-sm font-bold text-[#1d2a57] outline-none transition placeholder:text-[#c5cfe0] focus:border-[#7fb1a8] focus:ring-2 focus:ring-[#eef5f4]"
        />
      </div>
    </div>
  );
}
