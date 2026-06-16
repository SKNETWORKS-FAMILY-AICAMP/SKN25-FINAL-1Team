import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useHospitalStore } from "../stores/hospital-store";

/**
 * 인증된 보호자의 등록 병원을 최초 1회 로드하고,
 * 등록 병원이 0개면 온보딩 전용 페이지로 강제 이동시킨다.
 * (백엔드 오류 등 error 상태에서는 앱을 막지 않고 통과시킨다.)
 */
const OnboardingGate = () => {
  const status = useHospitalStore((state) => state.status);
  const myHospitals = useHospitalStore((state) => state.myHospitals);
  const load = useHospitalStore((state) => state.load);
  const location = useLocation();

  useEffect(() => {
    if (status === "idle") {
      void load();
    }
  }, [status, load]);

  if (status === "idle" || status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
      </div>
    );
  }

  if (status === "ready" && myHospitals.length === 0) {
    return <Navigate to="/onboarding" replace state={{ from: location }} />;
  }

  return <Outlet />;
};

export default OnboardingGate;
