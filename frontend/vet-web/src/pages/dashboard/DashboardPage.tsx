import { useEffect, useMemo, useState } from "react";
import {
  getDashboardApiErrorMessage,
  getDashboardApiErrorStatus,
  getTodayDashboard,
} from "../../api/dashboardApi";
import type {
  DashboardScheduleItem,
  DashboardSummaries,
} from "../../api/dashboardApi";
import type { AuthSession } from "../../api/authApi";
import { DashboardSchedulePanel } from "../../components/dashboard/DashboardSchedulePanel";
import { DashboardSummaryCards } from "../../components/dashboard/DashboardSummaryCards";
import AppLayout, { type AppMenuId } from "../../layouts/AppLayout";
import {
  createSummaryCards,
  formatApiDate,
  formatSelectedDate,
} from "../../utils/dashboardUtils";
import { getHolidayName } from "../../utils/reservationUtils";

interface DashboardPageProps {
  session: AuthSession;
  onLogout: () => void;
  onNavigate: (menuId: AppMenuId) => void;
}

export default function DashboardPage({
  session,
  onLogout,
  onNavigate,
}: DashboardPageProps) {
  const [selectedDate] = useState(() => new Date());
  const [summaries, setSummaries] = useState<DashboardSummaries>({
    total: 0,
    waiting: 0,
    emergency: 0,
    completed: 0,
  });
  const [scheduleItems, setScheduleItems] = useState<DashboardScheduleItem[]>(
    []
  );
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const formattedDate = useMemo(
    () => formatSelectedDate(selectedDate),
    [selectedDate]
  );
  const holidayName = useMemo(() => getHolidayName(selectedDate), [selectedDate]);
  const apiDate = useMemo(() => formatApiDate(selectedDate), [selectedDate]);
  const summaryCards = useMemo(
    () => createSummaryCards(summaries),
    [summaries]
  );

  useEffect(() => {
    let cancelled = false;

    setIsLoading(true);
    setErrorMessage("");

    getTodayDashboard(session.accessToken, apiDate)
      .then((result) => {
        if (cancelled) return;
        setSummaries(result.summaries);
        setScheduleItems(result.schedules);
      })
      .catch((err) => {
        console.error("[dashboard] load failed", err);
        if (!cancelled) {
          const status = getDashboardApiErrorStatus(err);

          setSummaries({
            total: 0,
            waiting: 0,
            emergency: 0,
            completed: 0,
          });
          setScheduleItems([]);
          setErrorMessage(getDashboardApiErrorMessage(err));

          if (status === 401) {
            onLogout();
          }
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [session.accessToken, apiDate, onLogout]);

  return (
    <AppLayout
      session={session}
      activeMenu="home"
      onLogout={onLogout}
      onNavigate={onNavigate}
    >
      <div className="flex max-w-[1040px] items-start gap-4">
        <div className="flex w-40 shrink-0 flex-col gap-3">
          <div>
            <h1 className="text-xl font-extrabold tracking-normal text-[#151b28]">
              오늘의 진료 현황
            </h1>
            <p className="mt-1.5 text-sm font-bold tabular-nums text-[#6b7486]">
              {formattedDate}
              {holidayName && (
                <span className="ml-1 rounded-md bg-[#fff1f2] px-1.5 py-0.5 text-xs font-extrabold text-[#ef4444]">
                  {holidayName}
                </span>
              )}
            </p>
          </div>
          <DashboardSummaryCards summaries={summaryCards} />
        </div>
        <div className="flex-1">
          <DashboardSchedulePanel
            schedules={scheduleItems}
            isLoading={isLoading}
            errorMessage={errorMessage}
            holidayName={holidayName}
          />
        </div>
      </div>
    </AppLayout>
  );
}
