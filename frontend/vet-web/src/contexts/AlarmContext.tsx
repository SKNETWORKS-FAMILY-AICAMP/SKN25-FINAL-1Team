import axios from "axios";
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { AlarmItem, fetchAlarmList, markAllAlarmsRead } from "../api/alarmApi";
import { AuthSession } from "../api/authApi";
import { logger } from "../utils/logger";

// 알림 폴링 주기. 실패가 이어지면 BASE → MAX 로 점진 백오프했다가 성공 시 BASE 복귀.
const POLL_INTERVAL_MS = 30_000;
const POLL_MAX_INTERVAL_MS = 120_000;

interface AlarmContextValue {
  alarms: AlarmItem[];
  hasUnread: boolean;
  isMarkingRead: boolean;
  markAllRead: () => Promise<void>;
  visitedAlarmIds: Set<number>;
  markAsVisited: (id: number) => void;
}

const AlarmContext = createContext<AlarmContextValue>({
  alarms: [],
  hasUnread: false,
  isMarkingRead: false,
  markAllRead: async () => {},
  visitedAlarmIds: new Set(),
  markAsVisited: () => {},
});

export function AlarmProvider({
  session,
  children,
}: {
  session: AuthSession;
  children: ReactNode;
}) {
  const [alarms, setAlarms] = useState<AlarmItem[]>([]);
  const [isMarkingRead, setIsMarkingRead] = useState(false);

  const VISITED_KEY = `visitedAlarmIds_${session.user.id}`;

  const [visitedAlarmIds, setVisitedAlarmIds] = useState<Set<number>>(() => {
    try {
      const stored = localStorage.getItem(`visitedAlarmIds_${session.user.id}`);
      if (stored) return new Set(JSON.parse(stored) as number[]);
    } catch {}
    return new Set<number>();
  });

  const markAsVisited = (id: number) => {
    setVisitedAlarmIds((prev) => {
      const next = new Set([...prev, id]);
      try {
        localStorage.setItem(VISITED_KEY, JSON.stringify([...next]));
      } catch {}
      return next;
    });
  };

  useEffect(() => {
    // self-scheduling 폴링: 직전 요청이 끝난 뒤에야 다음 주기를 잡아 요청 겹침을 막는다.
    let cancelled = false; // 언마운트/세션 교체 후 늦게 도착한 응답을 무시
    let stopped = false; // 인증 만료(401) 시 영구 중단
    let timer: number | undefined;
    let failures = 0;

    const schedule = (delay: number) => {
      if (cancelled || stopped) return;
      timer = window.setTimeout(tick, delay);
    };

    async function tick() {
      if (cancelled || stopped) return;
      // 백그라운드 탭에서는 폴링을 건너뛴다(visibilitychange 핸들러가 복귀 시 즉시 갱신).
      if (document.visibilityState === "hidden") {
        schedule(POLL_INTERVAL_MS);
        return;
      }
      try {
        const list = await fetchAlarmList({ accessToken: session.accessToken });
        if (cancelled) return;
        setAlarms(list);
        failures = 0;
        schedule(POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        // 인증 만료: 백그라운드 폴러가 직접 로그아웃시키지 않고 폴링만 멈춘다.
        // (실제 로그아웃은 사용자 액션 API의 기존 401 처리에 위임)
        if (axios.isAxiosError(err) && err.response?.status === 401) {
          stopped = true;
          logger.warn("[Alarm] 인증 만료 — 폴링 중단");
          return;
        }
        // 일시적 오류: 기존 알림을 유지(빈 배열로 덮지 않음)하고 백오프 후 재시도.
        logger.error("[Alarm] fetch 실패:", err);
        failures += 1;
        schedule(Math.min(POLL_INTERVAL_MS * 2 ** (failures - 1), POLL_MAX_INTERVAL_MS));
      }
    }

    const handleVisibility = () => {
      // 탭이 다시 보이면 대기 중인 타이머를 취소하고 즉시 한 번 갱신.
      if (document.visibilityState === "visible" && !cancelled && !stopped) {
        window.clearTimeout(timer);
        tick();
      }
    };

    tick();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [session.accessToken]);

  // 더 이상 존재하지 않는 알림 ID를 visited에서 정리
  useEffect(() => {
    if (alarms.length === 0) return;
    const alarmIds = new Set(alarms.map((a) => a.alarmid));
    setVisitedAlarmIds((prev) => {
      const next = new Set([...prev].filter((id) => alarmIds.has(id)));
      try {
        localStorage.setItem(VISITED_KEY, JSON.stringify([...next]));
      } catch {}
      return next;
    });
  }, [alarms]);

  const markAllRead = async () => {
    setIsMarkingRead(true);
    try {
      await markAllAlarmsRead({ accessToken: session.accessToken });
    } catch {
      // API 실패해도 로컬 상태는 반영
    } finally {
      setAlarms((prev) => prev.map((a) => ({ ...a, is_read: true })));
      setIsMarkingRead(false);
    }
  };

  return (
    <AlarmContext.Provider
      value={{ alarms, hasUnread: alarms.some((a) => !a.is_read), isMarkingRead, markAllRead, visitedAlarmIds, markAsVisited }}
    >
      {children}
    </AlarmContext.Provider>
  );
}

export function useAlarms() {
  return useContext(AlarmContext);
}
