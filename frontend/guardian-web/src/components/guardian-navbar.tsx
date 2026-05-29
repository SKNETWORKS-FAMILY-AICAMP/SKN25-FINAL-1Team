import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuthStore } from "../stores/auth-store";
import medipawSymbol from "../../../shared/assets/logo/medipaw-symbol.png";

const navItems = [
  { label: "홈", to: "/home" },
  { label: "챗봇 상담", to: "/chatbot" },
  { label: "예약 내역", to: "/reservations" },
  { label: "마이페이지", to: "/mypage" },
];

const ChevronDownIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const MenuIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M3 12h18M3 6h18M3 18h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const XIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

interface GuardianNavbarProps {
  contentClassName?: string;
}

const GuardianNavbar = ({
  contentClassName = "max-w-[1200px] px-6",
}: GuardianNavbarProps) => {
  const navigate = useNavigate();
  const guardian = useAuthStore((state) => state.guardian);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const displayName = guardian?.name || guardian?.loginid || "보호자";
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

  return (
    <header className="sticky top-0 z-10 border-b border-slate-100 bg-white/95 backdrop-blur">
      <div
        className={[
          "mx-auto flex h-16 items-center justify-between",
          contentClassName,
        ].join(" ")}
      >
        <Link to="/home" className="flex items-center">
          <img src={medipawSymbol} alt="MediPaw" className="h-9 w-auto" />
        </Link>

        {/* 데스크톱 nav — lg(1024px) 이상에서만 표시 */}
        <nav className="hidden h-full items-center gap-8 lg:flex">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                [
                  "flex h-full items-center border-b-2 px-1 text-sm font-bold transition",
                  isActive
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-600 hover:text-blue-600",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          {/* 햄버거 버튼 — lg 미만에서만 표시 */}
          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-50 lg:hidden"
            aria-label={isMobileMenuOpen ? "메뉴 닫기" : "메뉴 열기"}
          >
            {isMobileMenuOpen ? <XIcon /> : <MenuIcon />}
          </button>

          {/* 계정 드롭다운 — 이름만, 동그라미 없음 */}
          <details className="relative">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-full px-2 py-1 transition hover:bg-slate-50">
              <span className="max-w-28 truncate text-sm font-bold text-slate-600">
                {displayName}님
              </span>
              <span className="text-slate-400">
                <ChevronDownIcon />
              </span>
            </summary>
            <div className="absolute right-0 mt-2 w-40 rounded-2xl border border-slate-100 bg-white p-2 text-sm font-semibold shadow-xl shadow-slate-200/80">
              <Link
                to="/mypage"
                className="block rounded-xl px-3 py-2 text-slate-700 hover:bg-blue-50 hover:text-blue-600"
              >
                계정 관리
              </Link>
              <button
                type="button"
                onClick={handleLogout}
                className="block w-full rounded-xl px-3 py-2 text-left text-slate-700 hover:bg-blue-50 hover:text-blue-600"
              >
                로그아웃
              </button>
            </div>
          </details>
        </div>
      </div>

      {/* 모바일 메뉴 — 햄버거 클릭 시 아래로 펼쳐짐 */}
      {isMobileMenuOpen && (
        <nav className="border-t border-slate-100 bg-white lg:hidden">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setIsMobileMenuOpen(false)}
              className={({ isActive }) =>
                [
                  "block border-l-2 px-6 py-3 text-sm font-bold transition",
                  isActive
                    ? "border-blue-600 bg-blue-50 text-blue-600"
                    : "border-transparent text-slate-600 hover:bg-slate-50 hover:text-blue-600",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
};

export default GuardianNavbar;
