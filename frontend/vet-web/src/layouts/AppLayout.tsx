import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAlarms } from "../contexts/AlarmContext";
import { OperatingHoursProvider } from "../contexts/OperatingHoursContext";
import {
  Bell,
  Building2,
  CalendarCheck,
  CalendarClock,
  CalendarDays,
  CalendarX,
  CheckCheck,
  ChevronDown,
  ClipboardList,
  Clock3,
  Home,
  Settings,
  UsersRound,
} from "lucide-react";
import { AuthSession } from "../api/authApi";
import { AlarmItem, AlarmType } from "../api/alarmApi";
import medipawSymbol from "../../../shared/assets/logo/medipaw-symbol.png";

export type AppMenuId = "home" | "emr" | "reservation" | "patients" | "hospital-manage" | "settings";

const menuPathMap: Record<AppMenuId, string> = {
  home: "/home",
  emr: "/emr",
  reservation: "/reservation",
  patients: "/patients",
  "hospital-manage": "/hospital-manage",
  settings: "/settings",
};

interface AppLayoutProps {
  children: ReactNode;
  session: AuthSession;
  activeMenu?: AppMenuId;
  compact?: boolean;
  serviceName?: string;
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
  { id: "hospital-manage", label: "병원 관리", Icon: Building2 },
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
    bgCls: "bg-blue-50",
    iconCls: "text-blue-600",
    labelCls: "text-blue-700",
  },
  reservation_cancelled: {
    label: "예약 취소",
    Icon: CalendarX,
    bgCls: "bg-red-50",
    iconCls: "text-red-500",
    labelCls: "text-red-600",
  },
  reservation_updated: {
    label: "예약 수정",
    Icon: CalendarClock,
    bgCls: "bg-amber-50",
    iconCls: "text-amber-500",
    labelCls: "text-amber-700",
  },
  chart_ready: {
    label: "차트 준비",
    Icon: ClipboardList,
    bgCls: "bg-blue-50",
    iconCls: "text-blue-600",
    labelCls: "text-blue-700",
  },
  followup_received: {
    label: "경과 보고",
    Icon: ClipboardList,
    bgCls: "bg-slate-50",
    iconCls: "text-slate-500",
    labelCls: "text-slate-600",
  },
};

const fallbackAlarmTypeMeta = {
  label: "알림",
  Icon: Bell,
  bgCls: "bg-slate-50",
  iconCls: "text-slate-500",
  labelCls: "text-slate-600",
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
  activeMenu: _activeMenu = "home",
  compact = false,
  serviceName: _serviceName = "동물병원 의료 보조 시스템",
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
    <div className="h-screen overflow-hidden bg-slate-50 text-slate-800">
      <header
        className={`fixed inset-x-0 top-0 z-30 flex ${headerHeightClass} items-center justify-between border-b border-slate-200 bg-white px-3`}
      >
        <Link
          to="/home"
          className="flex items-center rounded-lg p-1"
          aria-label="홈으로 이동"
        >
          <PawLogo />
        </Link>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-2 text-xs font-bold tabular-nums text-slate-700 md:flex">
            <Clock3 className="h-4 w-4 text-blue-600" strokeWidth={2.1} />
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
              className="relative flex h-8 w-8 items-center justify-center rounded-lg border-l border-r border-slate-100 text-blue-600 transition hover:bg-slate-50 hover:text-blue-600"
            >
              <Bell className="h-4 w-4" strokeWidth={2.1} />
              {hasUnread && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-red-500" />
              )}
            </button>

            {isNotifOpen && (
              <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-[380px] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl">
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
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-extrabold text-slate-800 transition hover:bg-slate-50"
              aria-expanded={isHospitalMenuOpen}
            >
              <span>{hospitalName}</span>
              <ChevronDown className="h-4 w-4 text-slate-500" strokeWidth={2.2} />
            </button>

            {isHospitalMenuOpen && (
              <div className="absolute right-0 top-12 w-48 rounded-lg border border-slate-200 bg-white py-2 shadow-lg">
                <button
                  type="button"
                  onClick={() => { onNavigate?.("settings"); setIsHospitalMenuOpen(false); }}
                  className="block w-full px-4 py-2 text-left text-sm font-bold text-slate-700 hover:bg-slate-50"
                >
                  병원 설정
                </button>
                <button
                  type="button"
                  onClick={onLogout}
                  className="block w-full px-4 py-2 text-left text-sm font-bold text-slate-700 hover:bg-slate-50"
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
          className={`fixed bottom-0 left-0 ${topOffsetClass} z-20 flex ${sidebarWidthClass} flex-col justify-between border-r border-slate-200 bg-white px-2.5 py-3`}
        >
          <nav className="space-y-1.5" aria-label="주요 메뉴">
            {navigationItems.map(({ id, label, Icon }) => (
              <NavLink
                key={id}
                to={menuPathMap[id]}
                data-tour={`vet-nav-${id}`}
                className={({ isActive }) =>
                  [
                    "flex h-10 w-full items-center gap-2 rounded-lg px-2.5 text-left text-xs font-extrabold transition",
                    isActive
                      ? "bg-blue-50 text-blue-600"
                      : "text-slate-800 hover:bg-slate-50 hover:text-blue-600",
                  ].join(" ")
                }
              >
                <Icon className="h-4 w-4 shrink-0 text-blue-600" strokeWidth={2.2} />
                <span className="truncate">{label}</span>
              </NavLink>
            ))}
          </nav>

          <section className="rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm">
            <div>
              <p className="text-[10px] font-bold text-slate-600">수의사 계정</p>
              <p className="mt-0.5 truncate text-xs font-extrabold text-slate-800">
                {session.user.name}
              </p>
            </div>
            <div className="mt-2 border-t border-slate-100 pt-2">
              <p className="text-[10px] font-bold text-slate-600">마지막 로그인</p>
              <p className="mt-0.5 break-words text-[10px] font-extrabold tabular-nums text-slate-800">
                {lastLoginText}
              </p>
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="mt-2 h-8 w-full rounded-lg border border-slate-200 bg-white text-xs font-extrabold text-slate-600 transition hover:border-blue-500 hover:text-blue-600"
            >
              로그아웃
            </button>
          </section>
        </aside>

        <main
          className={`${sidebarMarginClass} flex-1 bg-slate-50 ${
            compact
              ? "h-[calc(100vh-56px)] overflow-hidden px-2 py-2"
              : "h-[calc(100vh-56px)] overflow-y-auto px-4 pb-8 pt-5"
          }`}
        >
          <OperatingHoursProvider session={session}>
            {children}
          </OperatingHoursProvider>
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
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3">
        <h3 className="text-sm font-extrabold text-slate-900">알림</h3>
        {hasUnread && (
          <button
            type="button"
            onClick={onMarkAllRead}
            disabled={isMarkingRead}
            className="flex items-center gap-1 text-xs font-bold text-blue-600 transition hover:text-blue-700 disabled:opacity-50"
          >
            <CheckCheck className="h-3.5 w-3.5" />
            모두 읽음
          </button>
        )}
      </div>

      {/* 목록 */}
      <ul className="flex-1 overflow-y-auto divide-y divide-slate-100">
        {alarms.length === 0 ? (
          <li className="flex flex-col items-center justify-center gap-3 py-14 text-sm font-bold text-slate-400">
            <Bell className="h-9 w-9 text-slate-300" strokeWidth={1.8} />
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
      className={`flex cursor-pointer items-start gap-3 px-4 py-3.5 transition hover:bg-slate-50 ${
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
          <span className="shrink-0 text-[10px] font-semibold text-slate-300">
            {formatAlarmTime(alarm.created_at)}
          </span>
        </div>
        <p className="mt-1 text-sm font-semibold leading-5 text-slate-800">
          {alarm.contents}
        </p>
      </div>

      {!alarm.is_read && (
        <div className="mt-2 h-2 w-2 shrink-0 rounded-full bg-blue-600" />
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
