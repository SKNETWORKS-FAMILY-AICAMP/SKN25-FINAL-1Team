import { useEffect, useState } from "react";

import { getMyHospitals } from "../api/hospital-api";
import { MOCK_HOSPITALS } from "../api/hospital-mock";

export interface MyHospitalItem {
  hospitalid: number;
  name: string;
}

/**
 * 보호자가 등록한 병원 목록(병원 전환용). 예약 모달·챗봇·병원탭 공용.
 * 백엔드 미가동 시 데모 목업으로 폴백해 화면이 깨지지 않게 한다.
 */
export function useMyHospitals() {
  const [hospitals, setHospitals] = useState<MyHospitalItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getMyHospitals()
      .then((list) => {
        if (mounted) setHospitals(list.map((h) => ({ hospitalid: h.hospitalid, name: h.name })));
      })
      .catch(() => {
        if (mounted) {
          setHospitals(MOCK_HOSPITALS.map((h) => ({ hospitalid: h.hospitalid, name: h.name })));
        }
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return { hospitals, isLoading };
}
