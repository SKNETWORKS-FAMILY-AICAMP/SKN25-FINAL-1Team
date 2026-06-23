import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getSchedules } from "../../api/schedule-api";
import { getPets, type Pet } from "../../api/pets-api";
import ActionButton from "../../components/common/action-button";
import PageHeader from "../../components/common/page-header";
import CancelScheduleModal from "../../components/schedule/cancel-schedule-modal";
import ChangeScheduleModal from "../../components/schedule/change-schedule-modal";
import ScheduleCard from "../../components/schedule/schedule-card";
import ScheduleSkeleton from "../../components/schedule/schedule-skeleton";
import ScheduleTabs from "../../components/schedule/schedule-tabs";
import {
  getErrorMessage,
  normalizeScheduleStatus,
  pageSize,
} from "../../components/schedule/schedule-utils";
import GuardianLayout from "../../layouts/guardian-layout";
import { useTranslation } from "../../i18n/language-context";
import type { ScheduleFilter, ScheduleListItem } from "../../types/schedule";

const InfoIcon = () => (
  <svg
    viewBox="0 0 24 24"
    className="h-4 w-4 shrink-0"
    fill="none"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
    <path
      d="M12 11v5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
    <circle cx="12" cy="8" r="1" fill="currentColor" />
  </svg>
);

const CalendarIcon = () => (
  <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" aria-hidden="true">
    <path
      d="M7 3v4M17 3v4M4 9h16M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const ScheduleListPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedFilter, setSelectedFilter] = useState<ScheduleFilter>("upcoming");
  const [pets, setPets] = useState<Pet[]>([]);
  const [selectedPetId, setSelectedPetId] = useState<number | null>(null);
  const [schedules, setSchedules] = useState<ScheduleListItem[]>([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [changeTarget, setChangeTarget] = useState<ScheduleListItem | null>(
    null,
  );
  const [cancelTarget, setCancelTarget] = useState<ScheduleListItem | null>(
    null,
  );
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  const loadSchedules = useCallback(async ({
    filter,
    petId,
    targetPage,
    append,
  }: {
    filter: ScheduleFilter;
    petId: number | null;
    targetPage: number;
    append: boolean;
  }) => {
    try {
      if (append) {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
      }

      setErrorMessage("");

      const response = await getSchedules({
        filter,
        petId,
        page: targetPage,
        size: pageSize,
      });

      if (response.code !== 200) {
        setErrorMessage(response.message || t("schedule.listError"));

        if (!append) {
          setSchedules([]);
        }

        return;
      }

      const filteredItems = response.result.items.filter(
        (schedule) => normalizeScheduleStatus(schedule.status) !== "PENDING",
      );

      setSchedules((currentSchedules) =>
        append ? [...currentSchedules, ...filteredItems] : filteredItems,
      );
      setPage(response.result.page);
      setHasNext(response.result.has_next);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, t("schedule.listError")));

      if (!append) {
        setSchedules([]);
      }
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [t]);

  const handleLoadMore = useCallback(() => {
    if (isLoadingMore || !hasNext) {
      return;
    }

    loadSchedules({
      filter: selectedFilter,
      petId: selectedPetId,
      targetPage: page + 1,
      append: true,
    });
  }, [hasNext, isLoadingMore, loadSchedules, page, selectedFilter, selectedPetId]);

  useEffect(() => {
    loadSchedules({
      filter: selectedFilter,
      petId: selectedPetId,
      targetPage: 1,
      append: false,
    });
  }, [loadSchedules, selectedFilter, selectedPetId]);

  useEffect(() => {
    // 드롭다운 옵션용 반려동물 목록. 실패해도 예약 목록 자체는 동작하므로 조용히 무시.
    getPets()
      .then((result) => setPets(result))
      .catch(() => setPets([]));
  }, []);

  useEffect(() => {
    const sentinel = loadMoreRef.current;
    if (!sentinel || !hasNext) {
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && !isLoading && !isLoadingMore) {
        handleLoadMore();
      }
    });
    observer.observe(sentinel);

    return () => observer.disconnect();
  }, [handleLoadMore, hasNext, isLoading, isLoadingMore]);

  const handleSelectFilter = (filter: ScheduleFilter) => {
    if (filter === selectedFilter) {
      return;
    }

    // 리스트를 비우지 않는다 — 새 데이터 도착 전까지 이전 탭 결과를 유지해
    // 풀 스켈레톤 깜빡임을 막는다. page/hasNext는 loadSchedules가 응답으로 갱신.
    setSelectedFilter(filter);
  };

  const handleRefreshAfterMutation = () => {
    setChangeTarget(null);
    setCancelTarget(null);

    loadSchedules({
      filter: selectedFilter,
      petId: selectedPetId,
      targetPage: 1,
      append: false,
    });
  };

  return (
    <GuardianLayout>
      <PageHeader
        title={t("schedule.title")}
        description={t("schedule.description")}
      />

      <section data-tour="guardian-reservations" className="w-full min-h-[480px] rounded-2xl border border-slate-100 bg-white px-4 pb-6 shadow-sm sm:px-8 sm:pb-8">
        <ScheduleTabs
          selectedFilter={selectedFilter}
          onSelectFilter={handleSelectFilter}
        />

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
            <InfoIcon />
            <span>{t("schedule.timeDisclaimer")}</span>
          </p>

          {pets.length > 0 ? (
            <select
              aria-label={t("schedule.petFilterAria")}
              value={selectedPetId ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                setSelectedPetId(value === "" ? null : Number(value));
              }}
              className="h-9 shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            >
              <option value="">{t("schedule.allPets")}</option>
              {pets.map((pet) => (
                <option key={pet.pet_id} value={pet.pet_id}>
                  {pet.petname}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <div className="py-6">
          {errorMessage ? (
            <div className="mb-4 rounded-xl bg-rose-50 px-4 py-3 text-sm font-bold text-rose-600">
              {errorMessage}
            </div>
          ) : null}

          {isLoading && schedules.length === 0 ? (
            <ScheduleSkeleton />
          ) : schedules.length === 0 ? (
            <div className="flex min-h-[360px] items-center justify-center py-16 text-center">
              <div>
                <div className="mx-auto flex h-[72px] w-[72px] items-center justify-center rounded-2xl bg-slate-50 text-slate-400">
                  <CalendarIcon />
                </div>

                <h2 className="mt-6 text-xl font-bold text-slate-800 sm:text-2xl">
                  {selectedFilter === "upcoming" && t("schedule.emptyUpcoming")}
                  {selectedFilter === "past" && t("schedule.emptyPast")}
                  {selectedFilter === "cancelled" && t("schedule.emptyCancelled")}
                </h2>

                {selectedFilter === "upcoming" ? (
                  <>
                    <p className="mt-3 text-sm font-semibold leading-6 text-slate-500">
                      {t("schedule.emptyHint")}
                    </p>
                    <ActionButton
                      type="button"
                      onClick={() => navigate("/chatbot")}
                      size="md"
                      className="mt-6"
                    >
                      {t("schedule.startChat")}
                    </ActionButton>
                  </>
                ) : null}
              </div>
            </div>
          ) : (
            // 탭 전환 재요청 중에는 이전 리스트를 유지하되 살짝 흐리게 + 스피너 표시.
            <div className="relative">
              <div
                className={
                  isLoading
                    ? "pointer-events-none space-y-4 opacity-40 transition-opacity"
                    : "space-y-4 transition-opacity"
                }
              >
                {schedules.map((schedule) => (
                  <ScheduleCard
                    key={schedule.schedule_id}
                    schedule={schedule}
                    onOpenChange={setChangeTarget}
                    onOpenCancel={setCancelTarget}
                  />
                ))}
              </div>

              {isLoading ? (
                <div className="absolute inset-0 flex items-start justify-center pt-24">
                  <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-100 border-t-blue-600" />
                </div>
              ) : null}
            </div>
          )}

          {!isLoading && hasNext ? (
            <div ref={loadMoreRef} className="mt-6 flex justify-center py-2">
              {isLoadingMore ? (
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-100 border-t-blue-600" />
              ) : (
                <span className="sr-only">{t("schedule.more")}</span>
              )}
            </div>
          ) : null}
        </div>
      </section>

      {changeTarget ? (
        <ChangeScheduleModal
          schedule={changeTarget}
          onClose={() => setChangeTarget(null)}
          onChanged={handleRefreshAfterMutation}
        />
      ) : null}

      {cancelTarget ? (
        <CancelScheduleModal
          schedule={cancelTarget}
          onClose={() => setCancelTarget(null)}
          onCancelled={handleRefreshAfterMutation}
        />
      ) : null}
    </GuardianLayout>
  );
};

export default ScheduleListPage;
