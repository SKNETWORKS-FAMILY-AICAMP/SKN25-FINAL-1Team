import ActionButton from "../common/action-button";
import ListItemCard from "../common/list-item-card";
import type { ScheduleFilter, ScheduleListItem } from "../../types/schedule";
import {
  canManageSchedule,
  formatScheduleTimeRange,
  getScheduleStatusLabelKey,
  getProfileImage,
  localeForLang,
  normalizeScheduleStatus,
} from "./schedule-utils";
import { useTranslation } from "../../i18n/language-context";
import { translateKnownText } from "../../i18n/known-text";

interface ScheduleCardProps {
  schedule: ScheduleListItem;
  selectedFilter: ScheduleFilter;
  onOpenChange: (schedule: ScheduleListItem) => void;
  onOpenCancel: (schedule: ScheduleListItem) => void;
}

const ScheduleCard = ({
  schedule,
  selectedFilter,
  onOpenChange,
  onOpenCancel,
}: ScheduleCardProps) => {
  const { t, lang } = useTranslation();
  const canManage = canManageSchedule(schedule);
  const normalizedStatus = normalizeScheduleStatus(schedule.status);

  // 확정 예약은 시간이 지나도 흐리게 처리하지 않는다.
  // 수의사가 실제로 진료완료(COMPLETED) 처리하기 전까지는 활성(예약 확정)으로 유지한다.
  const isInactive =
    selectedFilter === "all" &&
    (normalizedStatus === "COMPLETED" || normalizedStatus === "CANCELLED");
  const statusLabel = t(getScheduleStatusLabelKey(schedule.status));

  const badgeClassName =
    normalizedStatus === "CONFIRMED"
      ? "bg-sky-100 text-sky-600 ring-sky-200"
      : normalizedStatus === "CANCELLED"
        ? "bg-rose-100 text-rose-500 ring-rose-200"
        : "bg-slate-100 text-slate-500 ring-slate-200";

  return (
    <ListItemCard
      className={[
        "grid gap-4 transition hover:border-blue-100 hover:shadow-lg hover:shadow-blue-100/50",
        "lg:grid-cols-[88px_1fr_auto] lg:items-center lg:gap-6",
        isInactive ? "opacity-45 grayscale" : "",
      ].join(" ")}
    >
      <div className="h-20 w-20 overflow-hidden rounded-lg bg-slate-100">
        <img
          src={getProfileImage(schedule)}
          alt={t("common.petProfileAlt", { name: schedule.pet_name })}
          className="h-full w-full object-cover"
        />
      </div>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-extrabold text-slate-950">
            {schedule.pet_name}
          </h2>

          {statusLabel ? (
            <span
              className={`inline-flex h-5 items-center rounded-full px-2 text-[11px] font-bold ring-1 ${badgeClassName}`}
            >
              {statusLabel}
            </span>
          ) : null}
        </div>

        <p className="mt-2 text-base font-extrabold text-slate-900">
          {translateKnownText(schedule.category, t, lang)}
        </p>

        <p className="mt-1.5 text-sm font-bold text-blue-600">
          {formatScheduleTimeRange(
            schedule.confirmed_time,
            schedule.confirmed_end_time,
            localeForLang(lang),
          )}
        </p>
      </div>

      {canManage ? (
        <div className="flex flex-wrap items-center justify-start gap-2 lg:justify-end">
          <ActionButton
            type="button"
            onClick={() => onOpenChange(schedule)}
            variant="outlineBlue"
            size="sm"
            className="min-w-[96px] whitespace-nowrap rounded-lg"
          >
            {t("schedule.changeBooking")}
          </ActionButton>

          <ActionButton
            type="button"
            onClick={() => onOpenCancel(schedule)}
            variant="outlineDanger"
            size="sm"
            className="min-w-[96px] whitespace-nowrap rounded-lg"
          >
            {t("schedule.cancelBooking")}
          </ActionButton>
        </div>
      ) : null}
    </ListItemCard>
  );
};

export default ScheduleCard;
