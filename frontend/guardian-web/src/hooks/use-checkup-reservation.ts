import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";

import {
  getAvailableScheduleSlots,
  reserveCheckupSchedule,
} from "../api/schedule-api";
import type {
  ApiErrorResponse,
  AvailableScheduleSlot,
  CheckupReservationResult,
} from "../types/schedule";
import { useTranslation } from "../i18n/language-context";

const checkupDurationMin = 30;

const formatDateInput = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
};

const addMinutesToTime = (time: string, minutes: number) => {
  const [hour, minute] = time.split(":").map(Number);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) {
    return time;
  }

  const totalMinutes = hour * 60 + minute + minutes;
  const normalized = ((totalMinutes % 1440) + 1440) % 1440;
  const nextHour = String(Math.floor(normalized / 60)).padStart(2, "0");
  const nextMinute = String(normalized % 60).padStart(2, "0");
  return `${nextHour}:${nextMinute}`;
};

const getErrorMessage = (error: unknown, fallbackMessage: string) => {
  if (isAxiosError<ApiErrorResponse | string>(error)) {
    const responseData = error.response?.data;

    if (typeof responseData === "string") {
      try {
        return (
          (JSON.parse(responseData) as ApiErrorResponse).message ||
          fallbackMessage
        );
      } catch {
        return fallbackMessage;
      }
    }

    return responseData?.message || fallbackMessage;
  }

  return fallbackMessage;
};

interface UseCheckupReservationParams {
  petId: number;
  categoryCode?: number;
  // 다중 병원·원장: 선택된 병원/원장. doctorid 가 있으면 해당 원장의 슬롯만 조회·예약.
  hospitalId?: number;
  doctorId?: number;
}

export const useCheckupReservation = ({
  petId,
  categoryCode = 1,
  hospitalId,
  doctorId,
}: UseCheckupReservationParams) => {
  const { t } = useTranslation();
  const [selectedDate, setSelectedDateState] = useState(() =>
    formatDateInput(new Date()),
  );
  const [selectedSlot, setSelectedSlot] =
    useState<AvailableScheduleSlot | null>(null);
  const [memo, setMemo] = useState("");
  const [availableSlots, setAvailableSlots] = useState<AvailableScheduleSlot[]>(
    [],
  );
  const [isLoadingSlots, setIsLoadingSlots] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [completedReservation, setCompletedReservation] =
    useState<CheckupReservationResult | null>(null);
  const [slotsMessage, setSlotsMessage] = useState("");

  const setSelectedDate = useCallback((date: string) => {
    setSelectedDateState(date);
    setSelectedSlot(null);
  }, []);

  useEffect(() => {
    let isMounted = true;

    const loadAvailableSlots = async () => {
      try {
        setIsLoadingSlots(true);
        setErrorMessage("");

        const datePattern = /^\d{4}-\d{2}-\d{2}$/;
        if (!datePattern.test(selectedDate)) {
          if (isMounted) {
            setErrorMessage("정확한 날짜를 입력해주세요.");
            setAvailableSlots([]);
            setIsLoadingSlots(false);
          }
          return;
        }

        const [year, month, day] = selectedDate.split("-").map(Number);
        const dateObj = new Date(year, month - 1, day);
        if (
          dateObj.getFullYear() !== year ||
          dateObj.getMonth() + 1 !== month ||
          dateObj.getDate() !== day ||
          year < 2000 || year > 2100
        ) {
          if (isMounted) {
            setErrorMessage("정확한 날짜를 입력해주세요.");
            setAvailableSlots([]);
            setIsLoadingSlots(false);
          }
          return;
        }

        const response = await getAvailableScheduleSlots({
          date: selectedDate,
          duration_min: checkupDurationMin,
          doctorid: doctorId,
        });

        if (!isMounted) {
          return;
        }

        if (response.code !== 200) {
          setErrorMessage(
            response.message || t("schedule.slotsError"),
          );
          setAvailableSlots([]);
          setSlotsMessage("");
          return;
        }

        setAvailableSlots(response.result);
        setSlotsMessage(response.message || "");
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setErrorMessage(
          getErrorMessage(error, t("schedule.slotsError")),
        );
        setAvailableSlots([]);
      } finally {
        if (isMounted) {
          setIsLoadingSlots(false);
        }
      }
    };

    loadAvailableSlots();

    return () => {
      isMounted = false;
    };
    // 날짜 또는 원장이 바뀌면 슬롯을 다시 조회한다.
  }, [selectedDate, doctorId]);

  const reserveCheckup = async () => {
    if (!selectedSlot) {
      setErrorMessage(t("schedule.selectTimePrompt"));
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMessage("");

      const response = await reserveCheckupSchedule({
        pet_id: petId,
        date: selectedDate,
        time: selectedSlot.start_time,
        memo,
        category_code: categoryCode,
        hospitalid: hospitalId,
        doctorid: doctorId,
      });

      if ((response.code !== 200 && response.code !== 201) || !response.result) {
        setErrorMessage(response.message || t("schedule.checkupFailed"));
        return;
      }

      setCompletedReservation({
        ...response.result,
        end_time:
          response.result.end_time ||
          selectedSlot.end_time ||
          addMinutesToTime(response.result.time, checkupDurationMin),
        duration_min: response.result.duration_min || checkupDurationMin,
      });
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error, t("schedule.checkupFailed")),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    selectedDate,
    selectedSlot,
    memo,
    availableSlots,
    isLoadingSlots,
    isSubmitting,
    errorMessage,
    slotsMessage,
    completedReservation,
    setSelectedDate,
    setSelectedSlot,
    setMemo,
    reserveCheckup,
  };
};
