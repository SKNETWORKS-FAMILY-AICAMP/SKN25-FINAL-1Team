import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { searchHospitals, type HospitalSearchItem } from "../../api/hospital-api";
import { useHospitalStore } from "../../stores/hospital-store";
import { useAuthStore } from "../../stores/auth-store";
import ActionButton from "../../components/common/action-button";
import AuthLanguageSelector from "../../components/auth-language-selector";
import { useTranslation } from "../../i18n/language-context";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

const OnboardingPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const myHospitals = useHospitalStore((state) => state.myHospitals);
  const status = useHospitalStore((state) => state.status);
  const load = useHospitalStore((state) => state.load);
  const addHospital = useHospitalStore((state) => state.add);
  const clearAuth = useAuthStore((state) => state.clearAuth);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HospitalSearchItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [addingId, setAddingId] = useState<number | null>(null);

  // 직접 진입(병원 이미 있음)했거나 등록 직후 게이트 통과를 위해 최신 목록 보장.
  useEffect(() => {
    if (status === "idle") {
      void load();
    }
  }, [status, load]);

  // 입력 즉시 검색(디바운스). 버튼을 누르지 않아도 "메" → 메디포가 바로 뜬다.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSearched(false);
      setIsSearching(false);
      return;
    }
    let ignore = false;
    setIsSearching(true);
    const handle = window.setTimeout(() => {
      searchHospitals(q)
        .then((list) => {
          if (!ignore) setResults(list);
        })
        .catch(() => {
          if (!ignore) setResults([]);
        })
        .finally(() => {
          if (!ignore) {
            setSearched(true);
            setIsSearching(false);
          }
        });
    }, 250);
    return () => {
      ignore = true;
      window.clearTimeout(handle);
    };
  }, [query]);

  // 병원이 생기면(등록 완료) 홈으로 보낼 수 있도록 버튼만 활성화 — 자동 이동은 하지 않음.
  const hasHospital = myHospitals.length > 0;
  const registeredIds = new Set(myHospitals.map((h) => h.hospitalid));

  const handleSearch = async () => {
    if (!query.trim()) return;
    setIsSearching(true);
    setSearched(true);
    try {
      setResults(await searchHospitals(query.trim()));
    } catch {
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleAdd = async (hospitalid: number) => {
    setAddingId(hospitalid);
    try {
      await addHospital(hospitalid);
    } finally {
      setAddingId(null);
    }
  };

  const handleLogout = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#f8fafc] text-slate-900">
      <header className="mx-auto flex w-full max-w-3xl items-center justify-between px-4 py-4 sm:px-6">
        <img src={medipawSymbol} alt="MediPaw" className="h-8 w-auto sm:h-9" />
        <div className="flex items-center gap-3">
          <AuthLanguageSelector />
          <button
            type="button"
            onClick={handleLogout}
            className="text-sm font-bold text-slate-400 transition hover:text-slate-600"
          >
            {t("nav.logout")}
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-12 pt-6 sm:px-6">
        <div className="text-center">
          <h1 className="text-2xl font-extrabold text-slate-950 sm:text-3xl">
            {t("onboarding.title")}
          </h1>
          <p className="mx-auto mt-3 max-w-md text-sm font-semibold leading-6 text-slate-500">
            {t("onboarding.subtitle")}
          </p>
        </div>

        {/* 등록한 병원 */}
        {hasHospital ? (
          <ul className="mt-8 space-y-2">
            {myHospitals.map((h) => (
              <li
                key={h.hospitalid}
                className="flex items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3"
              >
                <span className="truncate text-sm font-bold text-slate-900">{h.name}</span>
                {h.is_primary ? (
                  <span className="shrink-0 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-bold text-blue-600">
                    {t("myHospitals.primaryBadge")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        {/* 병원 검색 */}
        <div className="mt-8 rounded-2xl border border-slate-100 bg-white p-5 shadow-sm sm:p-6">
          <p className="text-sm font-bold text-slate-800">{t("myHospitals.addTitle")}</p>
          <div className="mt-3 flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void handleSearch();
                }
              }}
              placeholder={t("myHospitals.searchPlaceholder")}
              className="h-11 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-900 outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
            />
            <ActionButton type="button" onClick={() => void handleSearch()} disabled={isSearching}>
              {t("myHospitals.search")}
            </ActionButton>
          </div>

          {searched ? (
            results.length === 0 ? (
              <p className="mt-4 text-sm font-semibold text-slate-400">
                {t("myHospitals.noResults")}
              </p>
            ) : (
              <ul className="mt-4 space-y-2">
                {results.map((r) => {
                  const isRegistered = registeredIds.has(r.hospitalid);
                  if (isRegistered) {
                    return (
                      <li
                        key={r.hospitalid}
                        className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold text-slate-900">{r.name}</p>
                          {r.address ? (
                            <p className="truncate text-xs font-semibold text-slate-400">{r.address}</p>
                          ) : null}
                        </div>
                        <span className="shrink-0 text-xs font-bold text-slate-400">
                          {t("myHospitals.added")}
                        </span>
                      </li>
                    );
                  }
                  return (
                    <li key={r.hospitalid}>
                      {/* 카드 전체가 클릭 영역 — 안의 "추가"는 시각 칩(span). */}
                      <button
                        type="button"
                        onClick={() => void handleAdd(r.hospitalid)}
                        disabled={addingId === r.hospitalid}
                        className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition hover:border-blue-300 hover:bg-blue-50/40 disabled:opacity-60"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold text-slate-900">{r.name}</p>
                          {r.address ? (
                            <p className="truncate text-xs font-semibold text-slate-400">{r.address}</p>
                          ) : null}
                        </div>
                        <span className="shrink-0 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white">
                          {t("myHospitals.add")}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )
          ) : null}
        </div>

        {/* 시작하기 */}
        <div className="mt-8 flex flex-col items-center gap-3">
          <ActionButton
            type="button"
            size="lg"
            disabled={!hasHospital}
            onClick={() => navigate("/home", { replace: true })}
            className="min-w-[200px]"
          >
            {t("onboarding.start")}
          </ActionButton>
          {!hasHospital ? (
            <p className="text-xs font-semibold text-slate-400">{t("onboarding.startHint")}</p>
          ) : null}
        </div>
      </main>
    </div>
  );
};

export default OnboardingPage;
