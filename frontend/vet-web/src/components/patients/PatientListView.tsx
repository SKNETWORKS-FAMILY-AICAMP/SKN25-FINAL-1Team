import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import type { PatientProfile } from "../../types/patient";
import { speciesOptions } from "../../utils/patientUtils";
import { EmptyState } from "../common/EmptyState";

interface PatientListViewProps {
  searchValue: string;
  selectedSpecies: string;
  currentPage: number;
  totalCount: number;
  totalPages: number;
  isLoading: boolean;
  patients: PatientProfile[];
  onSearch: (value: string) => void;
  onChangeSpecies: (value: string) => void;
  onChangePage: (page: number) => void;
  onOpenDetail: (patient: PatientProfile) => void;
}

export function PatientListView({
  searchValue,
  selectedSpecies,
  currentPage,
  totalCount,
  totalPages,
  isLoading,
  patients,
  onSearch,
  onChangeSpecies,
  onChangePage,
  onOpenDetail,
}: PatientListViewProps) {
  return (
    <div className="flex min-w-0 flex-col">
      <div className="mb-4 flex min-w-0 flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-extrabold text-slate-900">환자 관리</h1>
          <p className="mt-2 text-sm font-bold text-slate-500">
            병원 전체 환자 리스트를 확인하고 관리할 수 있습니다.
          </p>
        </div>

        <label className="relative w-full max-w-[420px]">
          <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500" />
          <input
            value={searchValue}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="강아지 이름 또는 보호자 이름 검색"
            className="h-12 w-full rounded-lg border border-slate-200 bg-white pl-12 pr-4 text-sm font-bold text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-blue-200 focus:ring-2 focus:ring-blue-50"
          />
        </label>
      </div>

      <section className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm h-[calc(100vh-184px)]">
        <div className="flex h-[64px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 xl:px-6">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-extrabold text-slate-900">전체 환자</h2>
            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-sm font-extrabold text-blue-600">
              {totalCount}
            </span>
          </div>

          <select
            value={selectedSpecies}
            onChange={(event) => onChangeSpecies(event.target.value)}
            className="h-11 min-w-[128px] rounded-lg border border-slate-200 bg-white px-3 text-sm font-extrabold text-slate-600 outline-none xl:min-w-[150px] xl:px-4"
          >
            <option value="all">전체</option>
            {speciesOptions.map((species) => (
              <option key={species} value={species}>
                {species}
              </option>
            ))}
          </select>
        </div>

        {patients.length === 0 ? (
          <EmptyState
            text={searchValue.trim() ? "검색 결과가 없습니다." : "환자가 없습니다."}
          />
        ) : (
          <>
            <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
              <table className="w-full table-fixed border-collapse text-left">
                <thead className="bg-slate-50">
                  <tr className="border-b border-slate-200 text-xs font-extrabold uppercase tracking-wide text-slate-400">
                    <th className="w-[18%] px-4 py-3.5 xl:w-[12%] xl:px-5">이름</th>
                    <th className="hidden w-[9%] px-3 py-3.5 xl:table-cell">나이</th>
                    <th className="w-[20%] px-3 py-3.5 xl:w-[13%]">보호자</th>
                    <th className="w-[22%] px-3 py-3.5 xl:w-[16%]">전화번호</th>
                    <th className="w-[22%] px-3 py-3.5 xl:w-[14%]">품종</th>
                    <th className="hidden w-[13%] px-3 py-3.5 xl:table-cell">최근 내원일</th>
                    <th className="hidden px-3 py-3.5 2xl:table-cell">메모</th>
                    <th className="w-[104px] px-4 py-3.5 xl:w-[120px]" aria-label="상세보기" />
                  </tr>
                </thead>
                <tbody>
                  {patients.map((patient) => (
                    <tr
                      key={patient.id}
                      onClick={() => !isLoading && onOpenDetail(patient)}
                      className="group h-[56px] cursor-pointer border-b border-slate-100 text-sm text-slate-700 last:border-b-0 transition-colors hover:bg-slate-50"
                    >
                      <td className="truncate px-4 py-3 font-extrabold text-slate-800 xl:px-5">
                        {patient.petName}
                      </td>
                      <td className="hidden px-3 py-3 text-slate-600 xl:table-cell">{patient.age}</td>
                      <td className="truncate px-3 py-3 font-semibold">{patient.guardianName}</td>
                      <td className="truncate px-3 py-3 tabular-nums text-slate-600">{patient.phone}</td>
                      <td className="px-3 py-3">
                        <span className="inline-flex max-w-full rounded-md bg-slate-50 px-2 py-0.5 text-xs font-extrabold text-slate-600">
                          <span className="truncate">
                            {patient.breed}
                          </span>
                        </span>
                      </td>
                      <td className="hidden px-3 py-3 tabular-nums text-slate-600 xl:table-cell">{patient.lastVisitDate}</td>
                      <td className="hidden truncate px-3 py-3 text-slate-400 2xl:table-cell">{patient.memo}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onOpenDetail(patient);
                          }}
                          disabled={isLoading}
                          className="h-9 w-[70px] whitespace-nowrap rounded-lg border border-blue-100 bg-white text-xs font-extrabold text-blue-600 transition hover:bg-blue-50 disabled:cursor-wait disabled:opacity-60 xl:w-[78px] xl:text-sm"
                        >
                          상세보기
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onChangePage={onChangePage}
            />
          </>
        )}
      </section>
    </div>
  );
}

function Pagination({
  currentPage,
  totalPages,
  onChangePage,
}: {
  currentPage: number;
  totalPages: number;
  onChangePage: (page: number) => void;
}) {
  const pages: Array<number | "..."> =
    totalPages <= 7
      ? Array.from({ length: totalPages }, (_, index) => index + 1)
      : [1, 2, 3, 4, 5, "...", totalPages];

  return (
    <div className="flex h-[56px] shrink-0 items-center justify-center gap-2 border-t border-slate-100 px-6">
      <button
        type="button"
        onClick={() => onChangePage(Math.max(1, currentPage - 1))}
        disabled={currentPage === 1}
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600 disabled:opacity-40"
        aria-label="이전 페이지"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      {pages.map((page) =>
        page === "..." ? (
          <span
            key="ellipsis"
            className="flex h-9 w-9 items-center justify-center text-sm font-extrabold text-slate-600"
          >
            ...
          </span>
        ) : (
          <button
            key={page}
            type="button"
            onClick={() => onChangePage(page)}
            className={[
              "h-9 w-9 rounded-lg text-sm font-extrabold",
              page === currentPage
                ? "bg-blue-50 text-blue-600"
                : "text-slate-600 hover:bg-slate-50",
            ].join(" ")}
          >
            {page}
          </button>
        )
      )}
      <button
        type="button"
        onClick={() => onChangePage(Math.min(totalPages, currentPage + 1))}
        disabled={currentPage === totalPages}
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600 disabled:opacity-40"
        aria-label="다음 페이지"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}
