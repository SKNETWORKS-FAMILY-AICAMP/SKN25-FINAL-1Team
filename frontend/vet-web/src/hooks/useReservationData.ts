import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDoctorPatientDetail,
  fetchDoctorPatientList,
  getPatientApiErrorMessage,
} from "../api/patientApi";
import { getReservations } from "../api/reservationApi";
import { fetchHospitalDoctors } from "../api/emrApi";
import type { DoctorInfo } from "../api/emrApi";
import type {
  ApiReservation,
  PatientsById,
  ReservationItem,
  ReservationPatient,
} from "../types/reservation";
import {
  mapApiReservations,
  mapPatientDetailToReservationPatient,
  mapPatientListItemToReservationPatient,
} from "../utils/reservationUtils";

export function useReservationData(accessToken: string) {
  const [reservations, setReservations] = useState<ReservationItem[]>([]);
  const [patientsById, setPatientsById] = useState<PatientsById>({});
  const [patientOptionsById, setPatientOptionsById] = useState<PatientsById>({});
  const [isLoading, setIsLoading] = useState(false);
  const [doctors, setDoctors] = useState<DoctorInfo[]>([]);

  const loadReservations = useCallback(async (doctorid?: number) => {
    setIsLoading(true);
    try {
      const data = await getReservations(doctorid);
      const items: ApiReservation[] = data?.result ?? [];
      const mapped = mapApiReservations(items);
      setReservations(mapped.reservations);
      setPatientsById(mapped.patientsById);
    } catch (error) {
      console.error("예약 목록 조회 실패:", error);
      setReservations([]);
      setPatientsById({});
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadPatientOptions = useCallback(async () => {
    try {
      // active_only=true: 모든 예약이 취소된(soft-deleted guardian만) 환자 제외
      const firstPage = await fetchDoctorPatientList({
        accessToken,
        page: 1,
        activeOnly: true,
      });
      const totalPage = firstPage.pagination?.total_page ?? 1;
      const restPages =
        totalPage > 1
          ? await Promise.all(
              Array.from({ length: totalPage - 1 }, (_, index) =>
                fetchDoctorPatientList({
                  accessToken,
                  page: index + 2,
                  activeOnly: true,
                })
              )
            )
          : [];
      const list = [firstPage, ...restPages].flatMap(
        (page) => page.patient_list ?? []
      );
      const optionsById: PatientsById = {};

      for (const item of list) {
        optionsById[item.petid] = mapPatientListItemToReservationPatient(item);
      }

      setPatientOptionsById(optionsById);
    } catch (error) {
      console.error("예약 환자 검색 목록 조회 실패:", error);
      alert(getPatientApiErrorMessage(error, "환자 검색 목록 조회에 실패했습니다."));
    }
  }, [accessToken]);

  const resolvePatientOption = useCallback(
    async (patient: ReservationPatient) => {
      try {
        const detail = await fetchDoctorPatientDetail({
          accessToken,
          petid: patient.id,
        });
        const resolvedPatient = mapPatientDetailToReservationPatient(
          detail,
          patient
        );

        setPatientOptionsById((current) => ({
          ...current,
          [resolvedPatient.id]: resolvedPatient,
        }));

        return resolvedPatient;
      } catch (error) {
        console.error("예약 환자 상세 조회 실패:", error);
        return patient;
      }
    },
    [accessToken]
  );

  useEffect(() => {
    // 토큰이 준비되기 전(auth store hydrate 전) 호출 시 401이 나므로 가드한다.
    if (!accessToken) return;
    loadReservations();
    loadPatientOptions();
    fetchHospitalDoctors(accessToken)
      .then(setDoctors)
      .catch((err) => console.error("[Reservation] doctor fetch failed:", err));
  }, [accessToken, loadPatientOptions, loadReservations]);

  const patientOptions = useMemo(
    () =>
      Object.values({ ...patientOptionsById, ...patientsById }).sort((a, b) =>
        a.petName.localeCompare(b.petName, "ko")
      ),
    [patientOptionsById, patientsById]
  );

  return {
    reservations,
    patientsById,
    patientOptions,
    doctors,
    isLoading,
    loadReservations,
    resolvePatientOption,
  };
}
