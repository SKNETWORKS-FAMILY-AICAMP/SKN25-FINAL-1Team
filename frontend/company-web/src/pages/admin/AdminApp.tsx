import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Building2, ClipboardList, LogOut, ShieldCheck, Stethoscope } from "lucide-react";

import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import AdminLogin from "./AdminLogin";
import ApplicationsList from "./ApplicationsList";
import ApplicationDetail from "./ApplicationDetail";
import HospitalsList from "./HospitalsList";
import HospitalManage from "./HospitalManage";
import ValidationPanel from "./ValidationPanel";
import JudgePanel from "./JudgePanel";
import { clearAdminToken, isAdminAuthed } from "../../onboarding/api";

const navClass = ({ isActive }: { isActive: boolean }) =>
  [
    "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-bold transition",
    isActive ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100",
  ].join(" ");

function AdminShell({ onLogout }: { onLogout: () => void }) {
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-800">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white p-4">
        <div className="flex items-center gap-2 px-2 py-2">
          <img src={medipawSymbol} alt="MediPaw" className="h-8 w-auto" />
          <span className="text-sm font-black text-slate-700">운영팀</span>
        </div>
        <nav className="mt-4 space-y-1">
          <NavLink to="/admin" end className={navClass}>
            <ClipboardList className="h-4 w-4" /> 입점 신청
          </NavLink>
          <NavLink to="/admin/hospitals" className={navClass}>
            <Building2 className="h-4 w-4" /> 병원 관리
          </NavLink>
          <NavLink to="/admin/validation" className={navClass}>
            <ShieldCheck className="h-4 w-4" /> Validation
          </NavLink>
          <NavLink to="/admin/judge" className={navClass}>
            <Stethoscope className="h-4 w-4" /> Judge
          </NavLink>
        </nav>
        <button
          type="button"
          onClick={onLogout}
          className="mt-auto flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-bold text-slate-500 transition hover:bg-slate-100"
        >
          <LogOut className="h-4 w-4" /> 로그아웃
        </button>
      </aside>

      <main className="flex-1 overflow-x-clip">
        <Routes>
          <Route index element={<ApplicationsList />} />
          <Route path="applications/:id" element={<ApplicationDetail />} />
          <Route path="hospitals" element={<HospitalsList />} />
          <Route path="hospitals/:id" element={<HospitalManage />} />
          <Route path="validation" element={<ValidationPanel />} />
          <Route path="judge" element={<JudgePanel />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function AdminApp() {
  const [authed, setAuthed] = useState(() => isAdminAuthed());

  if (!authed) {
    return <AdminLogin onLogin={() => setAuthed(true)} />;
  }

  return (
    <AdminShell
      onLogout={() => {
        clearAdminToken();
        setAuthed(false);
      }}
    />
  );
}
