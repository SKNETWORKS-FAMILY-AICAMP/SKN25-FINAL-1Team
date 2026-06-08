import type { ScheduleFilter } from "../../types/schedule";
import { scheduleTabs } from "./schedule-utils";
import { useTranslation } from "../../i18n/language-context";

interface ScheduleTabsProps {
  selectedFilter: ScheduleFilter;
  onSelectFilter: (filter: ScheduleFilter) => void;
}

const ScheduleTabs = ({
  selectedFilter,
  onSelectFilter,
}: ScheduleTabsProps) => {
  const { t } = useTranslation();

  return (
    <div className="flex gap-8 overflow-x-auto border-b border-slate-100">
      {scheduleTabs.map((tab) => (
        <button
          key={tab.filter}
          type="button"
          onClick={() => onSelectFilter(tab.filter)}
          className={[
            "h-14 shrink-0 border-b-2 px-1 text-sm font-extrabold transition",
            selectedFilter === tab.filter
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-600 hover:text-blue-600",
          ].join(" ")}
        >
          {t(tab.labelKey)}
        </button>
      ))}
    </div>
  );
};

export default ScheduleTabs;