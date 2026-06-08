import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuthStore } from "../stores/auth-store";
import { useTranslation } from "../i18n/language-context";
import { LANGUAGES } from "../i18n/translations";
import medipawSymbol from "../../../shared/assets/logo/medipaw-symbol.png";

const navItems = [
  { labelKey: "nav.home", to: "/home" },
  { labelKey: "nav.chatbot", to: "/chatbot" },
  { labelKey: "nav.reservations", to: "/reservations" },
  { labelKey: "nav.mypage", to: "/mypage" },
];

const ChevronDownIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const GlobeIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
    <path
      d="M3 12h18M12 3c2.5 2.5 3.8 5.7 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.7-3.8-9s1.3-6.5 3.8-9z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
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
  const { t, lang, setLang } = useTranslation();
  const guardian = useAuthStore((state) => state.guardian);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const displayName = guardian?.name || guardian?.loginid || t("nav.guardianFallback");
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isLangMenuOpen, setIsLangMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const langMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(e.target as Node)) {
        setIsAccountMenuOpen(false);
      }
      if (langMenuRef.current && !langMenuRef.current.contains(e.target as Node)) {
        setIsLangMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
              {t(item.labelKey)}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-1">
          {/* 햄버거 버튼 — lg 미만에서만 표시 */}
          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 transition hover:bg-slate-50 lg:hidden"
            aria-label={isMobileMenuOpen ? t("nav.closeMenu") : t("nav.openMenu")}
          >
            {isMobileMenuOpen ? <XIcon /> : <MenuIcon />}
          </button>

          {/* 언어 선택 — 지구본 아이콘 (계정 이름 왼쪽) */}
          <div ref={langMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setIsLangMenuOpen((v) => !v)}
              className="flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-50 hover:text-blue-600"
              aria-label={t("nav.language")}
              aria-haspopup="true"
              aria-expanded={isLangMenuOpen}
            >
              <GlobeIcon />
            </button>
            {isLangMenuOpen && (
              <div className="absolute right-0 mt-2 w-36 rounded-2xl border border-slate-100 bg-white p-2 text-sm font-semibold shadow-xl shadow-slate-200/80">
                {LANGUAGES.map((option) => (
                  <button
                    key={option.code}
                    type="button"
                    onClick={() => {
                      setLang(option.code);
                      setIsLangMenuOpen(false);
                    }}
                    className={[
                      "flex w-full items-center justify-between rounded-xl px-3 py-2 text-left transition",
                      lang === option.code
                        ? "bg-blue-50 text-blue-600"
                        : "text-slate-700 hover:bg-blue-50 hover:text-blue-600",
                    ].join(" ")}
                  >
                    <span>{option.nativeLabel}</span>
                    {lang === option.code && <span aria-hidden="true">✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 계정 드롭다운 — 이름만, 동그라미 없음 */}
          <div ref={accountMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setIsAccountMenuOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-full px-2 py-1 transition hover:bg-slate-50"
            >
              <span className="max-w-28 truncate text-sm font-bold text-slate-600">
                {displayName}
                {t("nav.accountSuffix")}
              </span>
              <span className="text-slate-400">
                <ChevronDownIcon />
              </span>
            </button>
            {isAccountMenuOpen && (
              <div className="absolute right-0 mt-2 w-40 rounded-2xl border border-slate-100 bg-white p-2 text-sm font-semibold shadow-xl shadow-slate-200/80">
                <Link
                  to="/mypage"
                  onClick={() => setIsAccountMenuOpen(false)}
                  className="block rounded-xl px-3 py-2 text-slate-700 hover:bg-blue-50 hover:text-blue-600"
                >
                  {t("nav.accountManage")}
                </Link>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="block w-full rounded-xl px-3 py-2 text-left text-slate-700 hover:bg-blue-50 hover:text-blue-600"
                >
                  {t("nav.logout")}
                </button>
              </div>
            )}
          </div>
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
              {t(item.labelKey)}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
};

export default GuardianNavbar;
