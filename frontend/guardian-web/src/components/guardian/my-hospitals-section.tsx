import { useEffect, useState } from "react";

import { searchHospitals, type HospitalSearchItem } from "../../api/hospital-api";
import { useHospitalStore } from "../../stores/hospital-store";
import ActionButton from "../common/action-button";
import SectionCard from "../common/section-card";
import { useTranslation } from "../../i18n/language-context";

const MyHospitalsSection = () => {
  const { t } = useTranslation();

  // 등록 병원·기본 병원은 전역 store 단일 소스 — 여기서 바꾸면 홈/예약/병원탭에 함께 반영.
  const hospitals = useHospitalStore((state) => state.myHospitals);
  const status = useHospitalStore((state) => state.status);
  const load = useHospitalStore((state) => state.load);
  const addHospital = useHospitalStore((state) => state.add);
  const removeHospital = useHospitalStore((state) => state.remove);
  const setPrimary = useHospitalStore((state) => state.setPrimary);
  const isLoading = status === "idle" || status === "loading";

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HospitalSearchItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    if (status === "idle") {
      void load();
    }
  }, [status, load]);

  // 입력 즉시 검색(디바운스). 버튼을 누르지 않아도 부분일치로 바로 결과가 뜬다.
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

  const registeredIds = new Set(hospitals.map((h) => h.hospitalid));

  const handleAdd = async (hospitalid: number) => {
    await addHospital(hospitalid);
  };

  const handlePrimary = async (hospitalid: number) => {
    await setPrimary(hospitalid);
  };

  const handleRemove = async (hospitalid: number) => {
    await removeHospital(hospitalid);
  };

  return (
    <SectionCard className="mt-5">
      <div className="border-b border-slate-100 pb-5">
        <p className="text-sm font-bold text-slate-950">{t("myHospitals.title")}</p>
        <p className="mt-1 text-sm text-slate-500">{t("myHospitals.description")}</p>
      </div>

      {/* 등록 병원 목록 */}
      {isLoading ? (
        <div className="mt-5 h-16 animate-pulse rounded-xl bg-slate-100" />
      ) : hospitals.length === 0 ? (
        <p className="mt-5 rounded-xl bg-slate-50 px-4 py-5 text-center text-sm font-semibold text-slate-400">
          {t("myHospitals.empty")}
        </p>
      ) : (
        <ul className="mt-5 space-y-2">
          {hospitals.map((h) => (
            <li
              key={h.hospitalid}
              className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate text-sm font-bold text-slate-900">{h.name}</span>
                {h.is_primary ? (
                  <span className="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-600">
                    {t("myHospitals.primaryBadge")}
                  </span>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {!h.is_primary ? (
                  <button
                    type="button"
                    onClick={() => handlePrimary(h.hospitalid)}
                    className="text-xs font-bold text-slate-500 transition hover:text-blue-600"
                  >
                    {t("myHospitals.setPrimary")}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => handleRemove(h.hospitalid)}
                  className="text-xs font-bold text-slate-400 transition hover:text-rose-500"
                >
                  {t("myHospitals.remove")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* 병원 추가 */}
      <div className="mt-6">
        <p className="mb-2 text-sm font-bold text-slate-800">{t("myHospitals.addTitle")}</p>
        <div className="flex gap-2">
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
            <p className="mt-3 text-sm font-semibold text-slate-400">
              {t("myHospitals.noResults")}
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
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
                      onClick={() => handleAdd(r.hospitalid)}
                      className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition hover:border-blue-300 hover:bg-blue-50/40"
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
    </SectionCard>
  );
};

export default MyHospitalsSection;
