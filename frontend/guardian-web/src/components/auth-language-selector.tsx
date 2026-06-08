import { useEffect, useRef, useState } from "react";

import { useTranslation } from "../i18n/language-context";
import { LANGUAGES } from "../i18n/translations";

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

const AuthLanguageSelector = () => {
  const { t, lang, setLang } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-50 hover:text-blue-600"
        aria-label={t("nav.language")}
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        <GlobeIcon />
      </button>
      {isOpen && (
        <div className="absolute right-0 z-20 mt-2 w-36 rounded-2xl border border-slate-100 bg-white p-2 text-sm font-semibold shadow-xl shadow-slate-200/80">
          {LANGUAGES.map((option) => (
            <button
              key={option.code}
              type="button"
              onClick={() => {
                setLang(option.code);
                setIsOpen(false);
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
  );
};

export default AuthLanguageSelector;
