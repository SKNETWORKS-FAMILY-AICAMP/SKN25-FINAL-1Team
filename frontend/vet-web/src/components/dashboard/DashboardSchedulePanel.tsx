import { useMemo } from "react";
import type { DashboardScheduleItem } from "../../api/dashboardApi";
import { useOperatingHoursForDate } from "../../contexts/OperatingHoursContext";
import { Panel } from "../common/Panel";
import { TriageBadge } from "../common/TriageBadge";
import { ClinicRoomIcon } from "./DashboardIcons";
import { visitTypeStyle } from "../../utils/dashboardUtils";
import {
  TIMELINE_MIN_CARD_HEIGHT,
  type PositionedTimelineItem,
  buildPositionedTimelineItems,
  getHourTicks,
  getLunchBlockMetrics,
  getScaledTimelineHeight,
  getTimelineRange,
} from "../../utils/scheduleTimelineUtils";

const DASHBOARD_TIMELINE_HOUR_HEIGHT = 56;

interface DashboardSchedulePanelProps {
  schedules: DashboardScheduleItem[];
  isLoading: boolean;
  errorMessage: string;
  holidayName?: string;
}

const DEFAULT_HOURS = { startTime: "09:00", endTime: "18:00", lunchStart: "12:00", lunchEnd: "13:00" };

export function DashboardSchedulePanel({
  schedules,
  isLoading,
  errorMessage,
  holidayName,
}: DashboardSchedulePanelProps) {
  const today = useMemo(() => new Date(), []);
  const todayHours = useOperatingHoursForDate(today);
  const { startTime, endTime, lunchStart, lunchEnd } = todayHours ?? DEFAULT_HOURS;

  const timelineRange = useMemo(
    () => getTimelineRange(schedules, { startTime, endTime, lunchStart, lunchEnd }),
    [schedules, startTime, endTime, lunchStart, lunchEnd]
  );
  const timelineScale = useMemo(
    () => ({ hourHeight: DASHBOARD_TIMELINE_HOUR_HEIGHT }),
    []
  );
  const hourTicks = useMemo(
    () => getHourTicks(timelineRange, timelineScale),
    [timelineRange, timelineScale]
  );
  const timelineHeight = useMemo(
    () => getScaledTimelineHeight(timelineRange, timelineScale),
    [timelineRange, timelineScale]
  );
  const lunchBlock = useMemo(
    () => getLunchBlockMetrics(timelineRange, { ...timelineScale, lunchStart, lunchEnd }),
    [timelineRange, timelineScale, lunchStart, lunchEnd]
  );
  const positionedSchedules = useMemo(
    () => buildPositionedTimelineItems(schedules, timelineRange, timelineScale),
    [schedules, timelineRange, timelineScale]
  );

  return (
    <Panel>
      <div className="flex items-center gap-4 border-b border-slate-100 px-5 py-3">
        <h2 className="text-lg font-extrabold tracking-normal text-slate-900">
          오늘의 일정
        </h2>
        {holidayName && (
          <span className="rounded-md bg-red-50 px-2 py-1 text-xs font-extrabold text-red-500">
            {holidayName}
          </span>
        )}
        <div className="hidden items-center gap-2 text-sm font-extrabold text-slate-600 lg:flex">
          <ClinicRoomIcon />
          <span>진료실 1</span>
          <span className="text-xs font-bold text-slate-500">
            수의사: 김보호
          </span>
        </div>
      </div>

      <div className="px-5 py-3">
        {errorMessage ? (
          <div className="mb-3 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-bold text-red-600">
            {errorMessage}
          </div>
        ) : null}

        {isLoading ? (
          <div className="mb-3 rounded-lg border border-slate-100 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-500">
            일정을 불러오는 중입니다.
          </div>
        ) : null}

        {todayHours === null && !isLoading && (
          <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-400">
            오늘은 휴진입니다.
          </div>
        )}

        <div className="grid grid-cols-[56px_1fr] gap-2">
          <div className="relative" style={{ height: timelineHeight }}>
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 text-xs font-extrabold tabular-nums text-slate-600"
                style={{ top: tick.top }}
              >
                {tick.label}
              </div>
            ))}
          </div>

          <div
            className="relative overflow-hidden rounded-lg border border-slate-100 bg-white"
            style={{ height: timelineHeight }}
          >
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 right-0 border-t border-slate-100"
                style={{ top: tick.top }}
              />
            ))}

            <div
              className="absolute inset-x-0 flex items-center bg-slate-100 px-3 text-xs font-extrabold text-slate-600"
              style={{
                top: lunchBlock.top,
                height: lunchBlock.height,
              }}
            >
              {lunchBlock.timeLabel}
              <span className="ml-5">점심시간</span>
            </div>

            {positionedSchedules.map((positioned) => (
              <ScheduleRow key={positioned.item.id} positioned={positioned} />
            ))}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function ScheduleRow({
  positioned,
}: {
  positioned: PositionedTimelineItem<DashboardScheduleItem>;
}) {
  const { item, top, height, timeLabel, columnIndex, columnCount } = positioned;
  const typeStyle = visitTypeStyle[item.type];

  return (
    <article
      className={`absolute z-10 flex items-center justify-between gap-3 overflow-hidden rounded-lg border py-2 pl-5 pr-3.5 text-left shadow-[0_4px_12px_rgba(15,23,42,0.08)] before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg ${typeStyle.card}`}
      style={{
        top,
        height: Math.max(height, TIMELINE_MIN_CARD_HEIGHT),
        left: `${(columnIndex / columnCount) * 100}%`,
        width: `calc(${100 / columnCount}% - ${columnCount > 1 ? 4 : 0}px)`,
      }}
    >
      <div
        className={[
          "grid min-w-0 flex-1 items-center gap-4",
          "grid-cols-[92px_minmax(100px,1fr)]",
        ].join(" ")}
      >
        <p className="text-xs font-extrabold tabular-nums text-slate-600">
          {timeLabel}
        </p>
        <div className="min-w-0">
          <p className="truncate text-sm font-extrabold text-slate-800">
            {item.patientName} ({item.species})
          </p>
        </div>
      </div>
      <TriageBadge level={item.type} />
    </article>
  );
}
