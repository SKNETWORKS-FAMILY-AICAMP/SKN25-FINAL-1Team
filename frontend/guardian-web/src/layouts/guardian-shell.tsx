import { Outlet } from "react-router-dom";

import GuardianNavbar from "../components/guardian-navbar";
import ProductTour from "../components/product-tour";

/**
 * 보호자 화면 공유 셸.
 * 네비바를 라우터 상위에서 단 한 번만 마운트하고, 화면 전환 시
 * <Outlet /> 안쪽의 <main>만 교체되도록 한다. (페이지마다 네비바를
 * 재마운트하던 깜빡임 제거)
 */
const GuardianShell = () => {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-950">
      <GuardianNavbar />
      <Outlet />
      <ProductTour />
    </div>
  );
};

export default GuardianShell;
