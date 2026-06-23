import { Suspense, lazy, useEffect } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { AuthSession } from "../api/authApi";
import ProductTour from "../components/ProductTour";
import { AppMenuId } from "../layouts/AppLayout";
import AccountInquiryPage from "../pages/auth/AccountInquiryPage";
import FindPasswordPage from "../pages/auth/FindPasswordPage";
import FirstPasswordChangePage from "../pages/auth/FirstPasswordChangePage";
import LoginPage from "../pages/auth/LoginPage";
import { useAuthStore } from "../stores/auth-store";
import ProtectedRoute from "./protected-route";

// 인증 후 페이지는 지연 로딩(코드 스플리팅) — 초기 번들에서 분리해 첫 로딩을 단축한다.
// (로그인/비밀번호 등 진입 경로 페이지는 정적 import 유지)
const DashboardPage = lazy(() => import("../pages/dashboard/DashboardPage"));
const EmrPage = lazy(() => import("../pages/emr/EmrPage"));
const PatientManagementPage = lazy(() => import("../pages/patients/PatientManagementPage"));
const ReservationPage = lazy(() => import("../pages/reservation/ReservationPage"));
const HospitalManagePage = lazy(() => import("../pages/hospital/HospitalManagePage"));
const SettingsPage = lazy(() => import("../pages/settings/SettingsPage"));

const devSession: AuthSession = {
  accessToken: "dev-preview-token",
  refreshToken: "dev-preview-refresh-token",
  lastLoginAt: new Date().toISOString(),
  user: {
    id: "dev-vet",
    name: "김보호",
    hospitalName: "MediPaw 동물병원",
    role: "VETERINARIAN",
    isFirstLogin: false,
  },
};

const menuPathMap: Record<AppMenuId, string> = {
  home: "/home",
  emr: "/emr",
  reservation: "/reservation",
  patients: "/patients",
  "hospital-manage": "/hospital-manage",
  settings: "/settings",
};

function getDevPath(search: string) {
  const devPage = new URLSearchParams(search).get("devPage");

  if (devPage === "home" || devPage === "dashboard") {
    return "/home";
  }

  if (devPage === "emr") {
    return "/emr";
  }

  if (devPage === "reservation") {
    return "/reservation";
  }

  if (devPage === "patients") {
    return "/patients";
  }

  if (devPage === "settings") {
    return "/settings";
  }

  return null;
}

function VetRoutes() {
  const navigate = useNavigate();
  const location = useLocation();
  const { session, setSession, clearAuth } = useAuthStore();

  useEffect(() => {
    // dev 미리보기 백도어(?devPage=)는 개발 빌드에서만 동작 — prod 번들엔 무효.
    if (!import.meta.env.DEV) {
      return;
    }

    const devPath = getDevPath(location.search);

    if (!devPath) {
      return;
    }

    setSession(devSession, { persist: false });
    navigate(devPath, { replace: true });
  }, [location.search, navigate, setSession]);

  const handleLoginSuccess = (nextSession: AuthSession) => {
    setSession(nextSession);
    navigate(
      nextSession.user.isFirstLogin ? "/first-password-change" : "/home",
      { replace: true }
    );
  };

  const handlePasswordChanged = (changedSession: AuthSession) => {
    setSession(changedSession);
    navigate("/home", { replace: true });
  };

  const handleGoLogin = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

  const handleLogout = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

  const handleNavigate = (menuId: AppMenuId, state?: Record<string, unknown>) => {
    navigate(menuPathMap[menuId], { state });
  };

  const protectedPageProps = {
    session: session!,
    onLogout: handleLogout,
    onNavigate: handleNavigate,
  };

  return (
    <Suspense fallback={<div style={{ padding: 24 }}>불러오는 중…</div>}>
    <Routes>
      <Route
        path="/"
        element={<Navigate to={session ? "/home" : "/login"} replace />}
      />
      <Route
        path="/login"
        element={
          session && !session.user.isFirstLogin ? (
            <Navigate to="/home" replace />
          ) : (
            <LoginPage onLoginSuccess={handleLoginSuccess} />
          )
        }
      />
      <Route path="/account-inquiry" element={<AccountInquiryPage />} />
      <Route path="/find-password" element={<FindPasswordPage />} />
      <Route
        path="/first-password-change"
        element={
          session ? (
            session.user.isFirstLogin ? (
              <FirstPasswordChangePage
                session={session}
                onPasswordChanged={handlePasswordChanged}
                onGoLogin={handleGoLogin}
              />
            ) : (
              <Navigate to="/home" replace />
            )
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />

      <Route element={<ProtectedRoute session={session} />}>
        <Route
          path="/home"
          element={<DashboardPage {...protectedPageProps} />}
        />
        <Route
          path="/dashboard"
          element={<Navigate to="/home" replace />}
        />
        <Route path="/emr" element={<EmrPage {...protectedPageProps} />} />
        <Route
          path="/reservation"
          element={<ReservationPage {...protectedPageProps} />}
        />
        <Route
          path="/patients"
          element={<PatientManagementPage {...protectedPageProps} />}
        />
        <Route
          path="/hospital-manage"
          element={<HospitalManagePage {...protectedPageProps} />}
        />
        <Route
          path="/settings"
          element={<SettingsPage {...protectedPageProps} />}
        />
      </Route>

      <Route
        path="*"
        element={<Navigate to={session ? "/home" : "/login"} replace />}
      />
    </Routes>
    {session && !session.user.isFirstLogin ? <ProductTour /> : null}
    </Suspense>
  );
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <VetRoutes />
    </BrowserRouter>
  );
}
