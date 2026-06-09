import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { fetchOperatingHours, fetchWeeklySchedule, type DaySchedule } from "../api/settingsApi";
import { AuthSession } from "../api/authApi";

export interface DayHours {
  startTime: string;
  endTime: string;
  lunchStart: string;
  lunchEnd: string;
}

interface OperatingHoursContextValue extends DayHours {
  weeklySchedule: DaySchedule[];
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
  });

  useEffect(() => {
    // 주간 스케줄 로드
    fetchWeeklySchedule(session.accessToken)
      .then((schedule) => {
        // 대표 시간: 첫 번째 영업 요일 기준 (기존 useOperatingHours 하위 호환)
        const firstOpen = schedule.find((d) => d.is_open && d.start_time);
        const rep = firstOpen
          ? {
              startTime: firstOpen.start_time!,
              endTime: firstOpen.end_time!,
              lunchStart: firstOpen.lunch_start ?? "12:00",
              lunchEnd: firstOpen.lunch_end ?? "13:00",
            }
          : defaultHours;
        setValue({ ...rep, weeklySchedule: schedule });
      })
      .catch(() => {
        // 주간 스케줄 실패 시 기존 단일 시간으로 fallback
        fetchOperatingHours(session.accessToken)
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

/** DailyTimeline용: 특정 날짜의 운영시간 반환. 휴진이면 null */
export function useOperatingHoursForDate(date: Date): DayHours | null {
  const { weeklySchedule } = useContext(OperatingHoursContext);

  // JS getDay(): 0=일, 1=월 ... 6=토 → 0=월 ... 6=일 변환
  const dow = (date.getDay() + 6) % 7;

  if (weeklySchedule.length === 0) {
    // 주간 스케줄 미설정: 기본값 (평일만 영업)
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
