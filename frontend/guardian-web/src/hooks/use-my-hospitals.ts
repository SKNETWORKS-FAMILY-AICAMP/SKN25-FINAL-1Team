import { useEffect } from "react";

import { useHospitalStore } from "../stores/hospital-store";

export interface MyHospitalItem {
  hospitalid: number;
  name: string;
}

/**
 * 보호자가 등록한 병원 목록(병원 전환용). 예약 모달·챗봇 공용.
 * 전역 hospital-store의 얇은 래퍼 — 단일 소스를 구독한다.
 */
export function useMyHospitals() {
  const hospitals = useHospitalStore((state) => state.myHospitals);
  const status = useHospitalStore((state) => state.status);
  const load = useHospitalStore((state) => state.load);

  useEffect(() => {
    if (status === "idle") {
      void load();
    }
  }, [status, load]);

  return {
    hospitals: hospitals.map((h) => ({ hospitalid: h.hospitalid, name: h.name })),
    isLoading: status === "idle" || status === "loading",
  };
}
