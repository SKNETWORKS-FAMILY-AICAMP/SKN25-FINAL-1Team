import { useEffect, useState } from "react";

import {
  addMyHospital,
  getMyHospitals,
  removeMyHospital,
  searchHospitals,
  setPrimaryHospital,
  type HospitalSearchItem,
  type MyHospital,
} from "../../api/hospital-api";
import ActionButton from "../common/action-button";
import SectionCard from "../common/section-card";
import { useTranslation } from "../../i18n/language-context";

const MyHospitalsSection = () => {
  const { t } = useTranslation();
  const [hospitals, setHospitals] = useState<MyHospital[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<HospitalSearchItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const reload = async () => {
    try {
      setHospitals(await getMyHospitals());
    } catch {
      // 백엔드 미가동 시 조용히 비움(데모)
      setHospitals([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

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
    await addMyHospital(hospitalid);
    await reload();
  };

  const handlePrimary = async (hospitalid: number) => {
    await setPrimaryHospital(hospitalid);
    await reload();
  };

  const handleRemove = async (hospitalid: number) => {
    await removeMyHospital(hospitalid);
    await reload();
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
              {results.map((r) => (
                <li
                  key={r.hospitalid}
                  className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-slate-900">{r.name}</p>
                    {r.address ? (
                      <p className="truncate text-xs font-semibold text-slate-400">{r.address}</p>
                    ) : null}
                  </div>
                  {registeredIds.has(r.hospitalid) ? (
                    <span className="shrink-0 text-xs font-bold text-slate-400">
                      {t("myHospitals.added")}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleAdd(r.hospitalid)}
                      className="shrink-0 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-blue-700"
                    >
                      {t("myHospitals.add")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )
        ) : null}
      </div>
    </SectionCard>
  );
};

export default MyHospitalsSection;
