import { useCallback, useEffect, useState } from "react";
import { logger } from "../utils/logger";
import {
  fetchDoctorPatientDetail,
  fetchDoctorPatientList,
} from "../api/patientApi";
import type {
  EmrHistoryRecord,
  PatientProfile,
} from "../types/patient";
import {
  mapDetailToHistory,
  mapDetailToPatient,
  mapListItemToPatient,
} from "../utils/patientUtils";

export function usePatientManagement(accessToken: string) {
  const [searchValue, setSearchValue] = useState("");
  const [selectedSpecies, setSelectedSpecies] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [pagePatients, setPagePatients] = useState<PatientProfile[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedPatient, setSelectedPatient] = useState<PatientProfile | null>(null);
  const [selectedHistory, setSelectedHistory] = useState<EmrHistoryRecord[]>([]);
  const [listRefreshKey, setListRefreshKey] = useState(0);

  useEffect(() => {
    // 토큰이 준비되기 전 호출 시 401이 나므로 가드한다.
    if (!accessToken) return;

    let isMounted = true;

    const loadPatients = async () => {
      setIsLoading(true);
      try {
        const result = await fetchDoctorPatientList({
          accessToken,
          page: currentPage,
          keyword: searchValue.trim(),
          species: selectedSpecies === "all" ? undefined : selectedSpecies,
        });

        if (!isMounted) {
          return;
        }

        setPagePatients(result.patient_list.map(mapListItemToPatient));
        setTotalCount(result.total_count ?? result.patient_list.length);
        setTotalPages(result.pagination?.total_page ?? 1);
      } catch (error) {
        logger.error(error);

        setPagePatients([]);
        setTotalCount(0);
        setTotalPages(1);
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadPatients();

    return () => {
      isMounted = false;
    };
  }, [accessToken, currentPage, listRefreshKey, searchValue, selectedSpecies]);

  const updateSearch = (value: string) => {
    setSearchValue(value);
    setCurrentPage(1);
  };

  const updateSpecies = (value: string) => {
    setSelectedSpecies(value);
    setCurrentPage(1);
  };

  const handleOpenDetailById = useCallback(async (patientId: number) => {
    try {
      const detail = await fetchDoctorPatientDetail({
        accessToken,
        petid: patientId,
      });

      setSelectedPatient(mapDetailToPatient(detail));
      setSelectedHistory(mapDetailToHistory(detail));
    } catch (error) {
      logger.error("환자 상세 조회 실패:", error);
    }
  }, [accessToken]);

  const handleOpenDetail = useCallback(async (patient: PatientProfile) => {
    await handleOpenDetailById(patient.id);
  }, [handleOpenDetailById]);

  const closeDetail = () => {
    setSelectedPatient(null);
    setSelectedHistory([]);
  };

  const handleSaved = (updated: PatientProfile) => {
    setSelectedPatient(updated);
    setListRefreshKey((prev) => prev + 1);
  };

  return {
    searchValue,
    selectedSpecies,
    currentPage,
    pagePatients,
    totalCount,
    totalPages,
    isLoading,
    selectedPatient,
    selectedHistory,
    setCurrentPage,
    updateSearch,
    updateSpecies,
    handleOpenDetail,
    handleOpenDetailById,
    closeDetail,
    handleSaved,
  };
}
