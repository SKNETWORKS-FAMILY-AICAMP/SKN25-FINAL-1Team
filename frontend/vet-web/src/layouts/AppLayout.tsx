import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useAlarms } from "../contexts/AlarmContext";
import {
  Bell,
  CalendarCheck,
  CalendarClock,
  CalendarDays,
  CalendarX,
  CheckCheck,
  ChevronDown,
  ClipboardList,
  Clock3,
  Home,
  Hospital,
  Settings,
  UsersRound,
} from "lucide-react";
import { AuthSession } from "../api/authApi";
import { AlarmItem, AlarmType } from "../api/alarmApi";
import medipawSymbol from "../../../shared/assets/logo/medipaw-symbol.png";

export type AppMenuId = "home" | "emr" | "reservation" | "patients" | "settings";

interface AppLayoutProps {
  children: ReactNode;
  session: AuthSession;
  activeMenu?: AppMenuId;
  compact?: boolean;
  serviceName?: string;
  /** @deprecated 알림은 내부에서 관리됩니다. */
  notificationCount?: number;
  onLogout: () => void;
  onNavigate?: (menuId: AppMenuId, state?: Record<string, unknown>) => void;
}

const navigationItems: Array<{
  id: AppMenuId;
  label: string;
  Icon: typeof Home;
}> = [
  { id: "home", label: "홈", Icon: Home },
  { id: "emr", label: "EMR", Icon: ClipboardList },
  { id: "reservation", label: "예약 관리", Icon: CalendarDays },
  { id: "patients", label: "환자 관리", Icon: UsersRound },
  { id: "settings", label: "설정", Icon: Settings },
];

const alarmTypeMeta: Record<
  AlarmType,
  {
    label: string;
    Icon: typeof CalendarCheck;
    bgCls: string;
    iconCls: string;
    labelCls: string;
  }
> = {
  reservation_confirmed: {
    label: "예약 확정",
    Icon: CalendarCheck,
    bgCls: "bg-[#eef5f4]",
    iconCls: "text-[#2f6f67]",
    labelCls: "text-[#255e57]",
  },
  reservation_cancelled: {
    label: "예약 취소",
    Icon: CalendarX,
    bgCls: "bg-[#fef2f2]",
    iconCls: "text-[#ef4444]",
    labelCls: "text-[#dc2626]",
  },
  reservation_updated: {
    label: "예약 수정",
    Icon: CalendarClock,
    bgCls: "bg-[#fffbeb]",
    iconCls: "text-[#f59e0b]",
    labelCls: "text-[#b45309]",
  },
  chart_ready: {
    label: "차트 준비",
    Icon: ClipboardList,
    bgCls: "bg-[#eef5f4]",
    iconCls: "text-[#2f6f67]",
    labelCls: "text-[#255e57]",
  },
  followup_received: {
    label: "경과 보고",
    Icon: ClipboardList,
    bgCls: "bg-[#f9fafb]",
    iconCls: "text-[#64748b]",
    labelCls: "text-[#475569]",
  },
};

const fallbackAlarmTypeMeta = {
  label: "알림",
  Icon: Bell,
  bgCls: "bg-[#f8fafb]",
  iconCls: "text-[#6b7895]",
  labelCls: "text-[#59657a]",
};

const dayLabels = ["일", "월", "화", "수", "목", "금", "토"];

function formatClock(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const weekday = dayLabels[date.getDay()];
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  const second = String(date.getSeconds()).padStart(2, "0");

  return `${year}.${month}.${day} (${weekday}) ${hour}:${minute}:${second}`;
}

function formatDateTime(value?: string) {
  if (!value) return "기록 없음";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "기록 없음";

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");

  return `${year}.${month}.${day} ${hour}:${minute}`;
}

function formatAlarmTime(dateStr: string) {
  const date = new Date(dateStr.replace(" ", "T"));
  const now = new Date();
  const diffMin = Math.floor((now.getTime() - date.getTime()) / 60000);

  if (diffMin < 1) return "방금";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}일 전`;

  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}`;
}

export default function AppLayout({
  children,
  session,
  activeMenu = "home",
  compact = false,
  serviceName = "동물병원 의료 보조 시스템",
  onLogout,
  onNavigate,
}: AppLayoutProps) {
  const [now, setNow] = useState(() => new Date());
  const [isHospitalMenuOpen, setIsHospitalMenuOpen] = useState(false);
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);

  const { alarms, hasUnread, isMarkingRead, markAllRead, visitedAlarmIds, markAsVisited } = useAlarms();

  useEffect(() => {
    const timerId = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timerId);
  }, []);

  // 패널 외부 클릭 시 닫기
  useEffect(() => {
    if (!isNotifOpen) return;

    const handleClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setIsNotifOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isNotifOpen]);

  const clockText = useMemo(() => formatClock(now), [now]);
  const hospitalName = session.user.hospitalName || "medipaw 동물병원";
  const lastLoginText = useMemo(
    () => formatDateTime(session.lastLoginAt),
    [session.lastLoginAt]
  );
  const headerHeightClass = "h-14";
  const topOffsetClass = "top-14";
  const contentPaddingTopClass = "pt-14";
  const sidebarWidthClass = "w-40";
  const sidebarMarginClass = "ml-40";

  return (
    <div className="h-screen overflow-hidden bg-[#f8fafc] text-[#1f2937]">
      <header
        className={`fixed inset-x-0 top-0 z-30 flex ${headerHeightClass} items-center justify-between border-b border-[#e5eaf2] bg-white px-3`}
      >
        <button
          type="button"
          onClick={() => onNavigate?.("home")}
          className="flex items-center rounded-lg p-1"
          aria-label="홈으로 이동"
        >
          <PawLogo />
        </button>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-2 text-xs font-bold tabular-nums text-[#3f4960] md:flex">
            <Clock3 className="h-4 w-4 text-[#2f6f67]" strokeWidth={2.1} />
            <span>{clockText}</span>
          </div>

          {/* 알림 버튼 */}
          <div className="relative" ref={notifRef}>
            <button
              type="button"
              onClick={() => {
                const willOpen = !isNotifOpen;
                setIsNotifOpen(willOpen);
                if (willOpen && hasUnread) markAllRead();
              }}
              aria-label="알림"
              className="relative flex h-8 w-8 items-center justify-center rounded-lg border-l border-r border-[#eef1f6] text-[#2f6f67] transition hover:bg-[#f8f9fa] hover:text-[#2f6f67]"
            >
              <Bell className="h-4 w-4" strokeWidth={2.1} />
              {hasUnread && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[#ef4444]" />
              )}
            </button>

            {isNotifOpen && (
              <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-[380px] overflow-hidden rounded-lg border border-[#e5eaf2] bg-white shadow-xl">
                <NotificationPanel
                  alarms={alarms}
                  isMarkingRead={isMarkingRead}
                  onMarkAllRead={markAllRead}
                  visitedAlarmIds={visitedAlarmIds}
                  onVisitAlarm={markAsVisited}
                  onNavigate={onNavigate}
                  onClose={() => setIsNotifOpen(false)}
                />
              </div>
            )}
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={() => setIsHospitalMenuOpen((isOpen) => !isOpen)}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-extrabold text-[#20283a] transition hover:bg-[#f8f9fa]"
              aria-expanded={isHospitalMenuOpen}
            >
              <span>{hospitalName}</span>
              <ChevronDown className="h-4 w-4 text-[#6b7895]" strokeWidth={2.2} />
            </button>

            {isHospitalMenuOpen && (
              <div className="absolute right-0 top-12 w-48 rounded-lg border border-[#dfe5ef] bg-white py-2 shadow-lg">
                <button
                  type="button"
                  onClick={() => { onNavigate?.("settings"); setIsHospitalMenuOpen(false); }}
                  className="block w-full px-4 py-2 text-left text-sm font-bold text-[#344055] hover:bg-[#f6f8f9]"
                >
                  병원 설정
                </button>
                <button
                  type="button"
                  onClick={onLogout}
                  className="block w-full px-4 py-2 text-left text-sm font-bold text-[#344055] hover:bg-[#f6f8f9]"
                >
                  로그아웃
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className={`flex ${contentPaddingTopClass}`}>
        <aside
          className={`fixed bottom-0 left-0 ${topOffsetClass} z-20 flex ${sidebarWidthClass} flex-col justify-between border-r border-[#e5eaf2] bg-white px-2.5 py-3`}
        >
          <nav className="space-y-1.5" aria-label="주요 메뉴">
            {navigationItems.map(({ id, label, Icon }) => {
              const isActive = id === activeMenu;

              return (
                <button
                  type="button"
                  key={id}
                  onClick={() => onNavigate?.(id)}
                  className={[
                    "flex h-10 w-full items-center gap-2 rounded-lg px-2.5 text-left text-xs font-extrabold transition",
                    isActive
                      ? "bg-[#eef5f4] text-[#2f6f67]"
                      : "text-[#20283a] hover:bg-[#f8fafb] hover:text-[#2f6f67]",
                  ].join(" ")}
                >
                  <Icon className="h-4 w-4 shrink-0 text-[#2f6f67]" strokeWidth={2.2} />
                  <span className="truncate">{label}</span>
                </button>
              );
            })}
          </nav>

          <section className="rounded-lg border border-[#e5eaf2] bg-white p-2.5 shadow-sm">
            <div className="flex items-start gap-2">
              <Hospital className="mt-0.5 h-4 w-4 shrink-0 text-[#357b70]" strokeWidth={2.1} />
              <div className="min-w-0">
                <p className="truncate text-xs font-extrabold text-[#20283a]">
                  {hospitalName}
                </p>
                <p className="mt-1 line-clamp-2 text-[10px] font-semibold leading-4 text-[#778196]">
                  서울특별시 강남구 테헤란로 123
                </p>
                <p className="mt-1 text-[10px] font-semibold text-[#778196]">
                  02-1234-5678
                </p>
              </div>
            </div>
            <div className="mt-2 border-t border-[#edf1f6] pt-2">
              <p className="text-[10px] font-bold text-[#4c5870]">수의사 계정</p>
              <p className="mt-0.5 truncate text-xs font-extrabold text-[#20283a]">
                {session.user.name}
              </p>
            </div>
            <div className="mt-2 border-t border-[#edf1f6] pt-2">
              <p className="text-[10px] font-bold text-[#4c5870]">마지막 로그인</p>
              <p className="mt-0.5 break-words text-[10px] font-extrabold tabular-nums text-[#20283a]">
                {lastLoginText}
              </p>
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="mt-2 h-8 w-full rounded-lg border border-[#dfe5ef] bg-white text-xs font-extrabold text-[#59657a] transition hover:border-[#357b70] hover:text-[#2f6f67]"
            >
              로그아웃
            </button>
          </section>
        </aside>

        <main
          className={`${sidebarMarginClass} flex-1 bg-[#f8fafc] ${
            compact
              ? "h-[calc(100vh-56px)] overflow-hidden px-2 py-2"
              : "h-[calc(100vh-56px)] overflow-y-auto px-4 pb-8 pt-5"
          }`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

function NotificationPanel({
  alarms,
  isMarkingRead,
  onMarkAllRead,
  visitedAlarmIds,
  onVisitAlarm,
  onNavigate,
  onClose,
}: {
  alarms: AlarmItem[];
  isMarkingRead: boolean;
  onMarkAllRead: () => void;
  visitedAlarmIds: Set<number>;
  onVisitAlarm: (id: number) => void;
  onNavigate?: (menuId: AppMenuId, state?: Record<string, unknown>) => void;
  onClose: () => void;
}) {
  const hasUnread = alarms.some((a) => !a.is_read);

  return (
    <div className="flex max-h-[520px] flex-col">
      {/* 헤더 */}
      <div className="flex shrink-0 items-center justify-between border-b border-[#e5eaf2] px-4 py-3">
        <h3 className="text-sm font-extrabold text-[#151b28]">알림</h3>
        {hasUnread && (
          <button
            type="button"
            onClick={onMarkAllRead}
            disabled={isMarkingRead}
            className="flex items-center gap-1 text-xs font-bold text-[#2f6f67] transition hover:text-[#255e57] disabled:opacity-50"
          >
            <CheckCheck className="h-3.5 w-3.5" />
            모두 읽음
          </button>
        )}
      </div>

      {/* 목록 */}
      <ul className="flex-1 overflow-y-auto divide-y divide-[#f0f3f8]">
        {alarms.length === 0 ? (
          <li className="flex flex-col items-center justify-center gap-3 py-14 text-sm font-bold text-[#8595ae]">
            <Bell className="h-9 w-9 text-[#c5cfe0]" strokeWidth={1.8} />
            알림이 없습니다.
          </li>
        ) : (
          alarms.map((alarm) => (
            <AlarmRow
              key={alarm.alarmid}
              alarm={alarm}
              isVisited={visitedAlarmIds.has(alarm.alarmid)}
              onNavigate={onNavigate}
              onClose={onClose}
              onVisitAlarm={onVisitAlarm}
            />
          ))
        )}
      </ul>
    </div>
  );
}

const emrAlarmTypes: AlarmType[] = ["chart_ready", "followup_received"];

function AlarmRow({
  alarm,
  isVisited,
  onNavigate,
  onClose,
  onVisitAlarm,
}: {
  alarm: AlarmItem;
  isVisited: boolean;
  onNavigate?: (menuId: AppMenuId, state?: Record<string, unknown>) => void;
  onClose: () => void;
  onVisitAlarm: (id: number) => void;
}) {
  const meta = alarmTypeMeta[alarm.type] ?? fallbackAlarmTypeMeta;
  const Icon = meta.Icon;

  const handleClick = () => {
    if (!onNavigate) return;
    onVisitAlarm(alarm.alarmid);
    const menuId: AppMenuId = emrAlarmTypes.includes(alarm.type) ? "emr" : "reservation";
    const state = menuId === "emr" ? { scheduleId: alarm.scheduleid } : undefined;
    onNavigate(menuId, state);
    onClose();
  };

  return (
    <li
      onClick={handleClick}
      className={`flex cursor-pointer items-start gap-3 px-4 py-3.5 transition hover:bg-[#f9fbfc] ${
        isVisited ? "opacity-60" : ""
      }`}
    >
      <div
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${meta.bgCls}`}
      >
        <Icon className={`h-4 w-4 ${meta.iconCls}`} strokeWidth={2} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className={`text-[11px] font-extrabold ${meta.labelCls}`}>
            {meta.label}
          </span>
          <span className="shrink-0 text-[10px] font-semibold text-[#b0b9cc]">
            {formatAlarmTime(alarm.created_at)}
          </span>
        </div>
        <p className="mt-1 text-sm font-semibold leading-5 text-[#1d2a57]">
          {alarm.contents}
        </p>
      </div>

      {!alarm.is_read && (
        <div className="mt-2 h-2 w-2 shrink-0 rounded-full bg-[#2f6f67]" />
      )}
    </li>
  );
}

function PawLogo() {
  return (
    <img
      src={medipawSymbol}
      alt="Medipaw"
      className="h-10 w-auto object-contain"
    />
  );
}
