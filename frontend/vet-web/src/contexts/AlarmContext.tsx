import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { AlarmItem, fetchAlarmList, markAllAlarmsRead } from "../api/alarmApi";
import { AuthSession } from "../api/authApi";

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
    fetchAlarmList({ accessToken: session.accessToken })
      .then(setAlarms)
      .catch((err) => { console.error("[Alarm] fetch failed:", err); setAlarms([]); });
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
