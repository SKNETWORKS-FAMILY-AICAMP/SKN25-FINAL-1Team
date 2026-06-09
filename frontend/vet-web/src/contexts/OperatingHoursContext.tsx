import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { fetchClosedDates, fetchOperatingHours, fetchWeeklySchedule, type DaySchedule } from "../api/settingsApi";
import { AuthSession } from "../api/authApi";

export interface DayHours {
  startTime: string;
  endTime: string;
  lunchStart: string;
  lunchEnd: string;
}

interface OperatingHoursContextValue extends DayHours {
  weeklySchedule: DaySchedule[];
  closedDates: string[];
}

const defaultHours: DayHours = {
  startTime: "09:00",
  endTime: "18:00",
  lunchStart: "12:00",
  lunchEnd: "13:00",
};

const OperatingHoursContext = createContext<OperatingHoursContextValue>({
  ...defaultHours,
  weeklySchedule: [],
  closedDates: [],
});

export function OperatingHoursProvider({
  session,
  children,
}: {
  session: AuthSession;
  children: ReactNode;
}) {
  const [value, setValue] = useState<OperatingHoursContextValue>({
    ...defaultHours,
    weeklySchedule: [],
    closedDates: [],
  });

  useEffect(() => {
    const token = session.accessToken;
    Promise.all([
      fetchWeeklySchedule(token),
      fetchClosedDates(token).catch(() => [] as string[]),
    ])
      .then(([schedule, dates]) => {
        const firstOpen = schedule.find((d) => d.is_open && d.start_time);
        const rep = firstOpen
          ? {
              startTime: firstOpen.start_time!,
              endTime: firstOpen.end_time!,
              lunchStart: firstOpen.lunch_start ?? "12:00",
              lunchEnd: firstOpen.lunch_end ?? "13:00",
            }
          : defaultHours;
        setValue({ ...rep, weeklySchedule: schedule, closedDates: dates });
      })
      .catch(() => {
        fetchOperatingHours(token)
          .then((data) =>
            setValue((prev) => ({
              ...prev,
              startTime: data.start_time,
              endTime: data.end_time,
              lunchStart: data.lunch_start,
              lunchEnd: data.lunch_end,
            }))
          )
          .catch(() => {});
      });
  }, [session.accessToken]);

  return (
    <OperatingHoursContext.Provider value={value}>
      {children}
    </OperatingHoursContext.Provider>
  );
}

/** 기존 컴포넌트용: 대표(첫 영업 요일) 시간 반환 */
export function useOperatingHours(): DayHours {
  const { startTime, endTime, lunchStart, lunchEnd } = useContext(OperatingHoursContext);
  return { startTime, endTime, lunchStart, lunchEnd };
}

/** WeeklySchedule용: 전체 7일 스케줄 배열 반환 */
export function useWeeklySchedule(): DaySchedule[] {
  return useContext(OperatingHoursContext).weeklySchedule;
}

/** 특정일 휴진 날짜 Set 반환 ("YYYY-MM-DD" 형식) */
export function useClosedDates(): Set<string> {
  const { closedDates } = useContext(OperatingHoursContext);
  return useMemo(() => new Set(closedDates), [closedDates]);
}

/** DailyTimeline용: 특정 날짜의 운영시간 반환. 휴진이면 null */
export function useOperatingHoursForDate(date: Date): DayHours | null {
  const { weeklySchedule, closedDates } = useContext(OperatingHoursContext);

  // 특정일 오버라이드 우선 확인
  const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  if (closedDates.includes(dateKey)) return null;

  // JS getDay(): 0=일, 1=월 ... 6=토 → 0=월 ... 6=일 변환
  const dow = (date.getDay() + 6) % 7;

  if (weeklySchedule.length === 0) {
    return dow >= 5 ? null : defaultHours;
  }

  const day = weeklySchedule.find((d) => d.day_of_week === dow);
  if (!day || !day.is_open) return null;

  return {
    startTime: day.start_time ?? "09:00",
    endTime: day.end_time ?? "18:00",
    lunchStart: day.lunch_start ?? "12:00",
    lunchEnd: day.lunch_end ?? "13:00",
  };
}
