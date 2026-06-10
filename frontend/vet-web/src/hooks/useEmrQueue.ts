import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchEmrQueue, fetchHospitalDoctors } from "../api/emrApi";
import type { DoctorInfo } from "../api/emrApi";
import type { QueuePatient, QueueTab } from "../types/emr";

const DATE_MS = 24 * 60 * 60 * 1000;

export function toDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function addDays(dateValue: string, days: number) {
  const date = new Date(`${dateValue}T00:00:00`);
  date.setDate(date.getDate() + days);
  return toDateInputValue(date);
}

function formatQueueDateLabel(dateValue: string) {
  const today = toDateInputValue(new Date());
  const diff =
    (new Date(`${dateValue}T00:00:00`).getTime() -
      new Date(`${today}T00:00:00`).getTime()) /
    DATE_MS;

  if (diff === 0) return "오늘";
  if (diff === -1) return "어제";
  if (diff === 1) return "내일";

  return new Date(`${dateValue}T00:00:00`).toLocaleDateString("ko-KR", {
    month: "long",
    day: "numeric",
  });
}

export function useEmrQueue(accessToken: string) {
  const todayValue = toDateInputValue(new Date());

  const [selectedDate, setSelectedDate] = useState(todayValue);
  const [queueTab, setQueueTab] = useState<QueueTab>("waiting");
  const [waitingQueue, setWaitingQueue] = useState<QueuePatient[]>([]);
  const [completedQueue, setCompletedQueue] = useState<QueuePatient[]>([]);
  const [isLoadingQueue, setIsLoadingQueue] = useState(false);
  const [selectedScheduleId, setSelectedScheduleId] = useState<number | undefined>(undefined);
  const [lastRefreshText, setLastRefreshText] = useState("방금 전");
  const [doctors, setDoctors] = useState<DoctorInfo[]>([]);
  const [selectedDoctorId, setSelectedDoctorId] = useState<number | undefined>(undefined);

  const isTodayView = selectedDate === todayValue;
  const currentQueue = queueTab === "waiting" ? waitingQueue : completedQueue;
  const queueDateLabel = formatQueueDateLabel(selectedDate);

  const queueTitle = useMemo(
    () =>
      queueTab === "waiting"
        ? `${queueDateLabel} ${waitingQueue.length}건 대기 중`
        : `${queueDateLabel} ${completedQueue.length}건 진료 완료`,
    [completedQueue.length, queueDateLabel, queueTab, waitingQueue.length]
  );

  useEffect(() => {
    if (!accessToken) return;
    fetchHospitalDoctors(accessToken)
      .then((list) => {
        setDoctors(list);
        if (list.length > 0 && selectedDoctorId === undefined) {
          setSelectedDoctorId(list[0].doctorid);
        }
      })
      .catch((err: unknown) => console.error("[HospitalDoctors] fetch failed:", err));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const loadQueue = useCallback(async () => {
    if (!accessToken) return;
    setIsLoadingQueue(true);
    try {
      const result = await fetchEmrQueue({ accessToken, date: selectedDate, doctorId: selectedDoctorId });
      setWaitingQueue(result.waiting);
      setCompletedQueue(result.completed);
      setSelectedScheduleId((prev) => {
        const combined = [...result.waiting, ...result.completed];
        if (prev !== undefined && combined.some((p) => p.schedule_id === prev)) return prev;
        return result.waiting[0]?.schedule_id ?? result.completed[0]?.schedule_id;
      });
    } catch (err) {
      console.error("[EMR Queue] fetch failed:", err);
    } finally {
      setIsLoadingQueue(false);
      setLastRefreshText(
        new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
      );
    }
  }, [accessToken, selectedDate, selectedDoctorId]);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  const handleChangeTab = useCallback(
    (tab: QueueTab) => {
      setQueueTab(tab);
      const queue = tab === "waiting" ? waitingQueue : completedQueue;
      setSelectedScheduleId(queue[0]?.schedule_id);
    },
    [waitingQueue, completedQueue]
  );

  return {
    selectedDate,
    setSelectedDate,
    isTodayView,
    queueTab,
    setQueueTab,
    waitingQueue,
    setWaitingQueue,
    completedQueue,
    setCompletedQueue,
    isLoadingQueue,
    selectedScheduleId,
    setSelectedScheduleId,
    lastRefreshText,
    currentQueue,
    queueTitle,
    loadQueue,
    handleChangeTab,
    doctors,
    selectedDoctorId,
    setSelectedDoctorId,
  };
}
