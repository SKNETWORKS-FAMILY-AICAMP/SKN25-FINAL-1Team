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
import type { DoctorInfo } from "../../api/emrApi";
import { fetchHospitalDoctors } from "../../api/emrApi";
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
  const [scheduleItems, setScheduleItems] = useState<DashboardScheduleItem[]>([]);
  const [doctors, setDoctors] = useState<DoctorInfo[]>([]);
  const [selectedDoctorId, setSelectedDoctorId] = useState<number | null>(null);
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

  const visibleSchedules = useMemo(
    () =>
      selectedDoctorId === null
        ? scheduleItems
        : scheduleItems.filter((s) => s.doctorid === selectedDoctorId),
    [scheduleItems, selectedDoctorId]
  );

  useEffect(() => {
    fetchHospitalDoctors(session.accessToken)
      .then(setDoctors)
      .catch(() => {});
  }, [session.accessToken]);

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

          setSummaries({ total: 0, waiting: 0, emergency: 0, completed: 0 });
          setScheduleItems([]);
          setErrorMessage(getDashboardApiErrorMessage(err));

          if (status === 401) {
            onLogout();
          }
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [session.accessToken, apiDate, onLogout]);

  const selectedDoctorName =
    selectedDoctorId === null
      ? undefined
      : doctors.find((d) => d.doctorid === selectedDoctorId)?.doctor_name ?? session.user.name;

  return (
    <AppLayout
      session={session}
      activeMenu="home"
      onLogout={onLogout}
      onNavigate={onNavigate}
    >
      <div className="flex min-h-[calc(100vh-160px)] min-w-0 flex-col overflow-y-auto">
        <div className="mb-4 flex min-w-0 items-start gap-6">
          <div className="min-w-0 shrink-0">
            <h1 className="text-2xl font-extrabold text-slate-900">
              오늘의 진료 현황
            </h1>
            <p className="mt-2 text-sm font-bold tabular-nums text-slate-500">
              {formattedDate}
              {holidayName && (
                <span className="ml-1 rounded-md bg-red-50 px-1.5 py-0.5 text-xs font-extrabold text-red-500">
                  {holidayName}
                </span>
              )}
            </p>
          </div>
          <DashboardSummaryCards summaries={summaryCards} className="pt-1" />

          {doctors.length > 0 && (
            <div className="ml-auto pt-1">
              <select
                value={selectedDoctorId ?? ""}
                onChange={(e) =>
                  setSelectedDoctorId(e.target.value === "" ? null : Number(e.target.value))
                }
                className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">전체 수의사</option>
                {doctors.map((doctor) => (
                  <option key={doctor.doctorid} value={doctor.doctorid}>
                    {doctor.doctor_name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <DashboardSchedulePanel
            schedules={visibleSchedules}
            isLoading={isLoading}
            errorMessage={errorMessage}
            holidayName={holidayName}
            doctorName={selectedDoctorName ?? session.user.name}
            doctors={doctors}
            selectedDoctorId={selectedDoctorId}
          />
        </div>
      </div>
    </AppLayout>
  );
}
