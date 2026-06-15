import { useMemo } from "react";
import type { DashboardScheduleItem } from "../../api/dashboardApi";
import type { DoctorInfo } from "../../api/emrApi";
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

const DOCTOR_COLORS = [
  { bar: "before:bg-teal-500", dot: "bg-teal-500" },
  { bar: "before:bg-orange-300", dot: "bg-orange-300" },
  { bar: "before:bg-indigo-400", dot: "bg-indigo-400" },
  { bar: "before:bg-amber-400", dot: "bg-amber-400" },
] as const;

type DoctorColor = (typeof DOCTOR_COLORS)[number];

interface DashboardSchedulePanelProps {
  schedules: DashboardScheduleItem[];
  isLoading: boolean;
  errorMessage: string;
  holidayName?: string;
  doctorName?: string;
  doctors?: DoctorInfo[];
  selectedDoctorId?: number | null;
}

const DEFAULT_HOURS = { startTime: "09:00", endTime: "18:00", lunchStart: "12:00", lunchEnd: "13:00" };

export function DashboardSchedulePanel({
  schedules,
  isLoading,
  errorMessage,
  holidayName,
  doctorName,
  doctors = [],
  selectedDoctorId = null,
}: DashboardSchedulePanelProps) {
  const today = useMemo(() => new Date(), []);
  const todayHours = useOperatingHoursForDate(today);
  const { startTime, endTime, lunchStart, lunchEnd } = todayHours ?? DEFAULT_HOURS;

  const isSplitMode = selectedDoctorId === null && doctors.length > 1;

  const singleDoctorColor = useMemo(() => {
    if (isSplitMode || selectedDoctorId === null) return undefined;
    const idx = doctors.findIndex((d) => d.doctorid === selectedDoctorId);
    if (idx === -1) return undefined;
    return DOCTOR_COLORS[idx % DOCTOR_COLORS.length];
  }, [isSplitMode, selectedDoctorId, doctors]);

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

  const perDoctorPositioned = useMemo(() => {
    if (!isSplitMode) return [];
    return doctors.map((doctor, colorIndex) => ({
      doctor,
      colorIndex,
      positioned: buildPositionedTimelineItems(
        schedules.filter((s) => s.doctorid === doctor.doctorid),
        timelineRange,
        timelineScale,
      ),
    }));
  }, [isSplitMode, doctors, schedules, timelineRange, timelineScale]);

  const positionedSchedules = useMemo(
    () => isSplitMode ? [] : buildPositionedTimelineItems(schedules, timelineRange, timelineScale),
    [isSplitMode, schedules, timelineRange, timelineScale]
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
            수의사: {doctorName ?? "-"}
          </span>
        </div>

        {isSplitMode && (
          <div className="ml-auto flex items-center gap-3">
            {doctors.map((doctor, i) => {
              const color = DOCTOR_COLORS[i % DOCTOR_COLORS.length];
              return (
                <div key={doctor.doctorid} className="flex items-center gap-1.5">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${color.dot}`} />
                  <span className="text-xs font-bold text-slate-600">{doctor.doctor_name}</span>
                </div>
              );
            })}
          </div>
        )}
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
              style={{ top: lunchBlock.top, height: lunchBlock.height }}
            >
              {lunchBlock.timeLabel}
              <span className="ml-5">점심시간</span>
            </div>

            {isSplitMode ? (
              <>
                {doctors.slice(0, -1).map((_, i) => (
                  <div
                    key={i}
                    className="absolute top-0 bottom-0 z-[3] border-l border-slate-100"
                    style={{ left: `${((i + 1) / doctors.length) * 100}%` }}
                  />
                ))}
                {perDoctorPositioned.map(({ colorIndex, positioned }) => {
                  const color = DOCTOR_COLORS[colorIndex % DOCTOR_COLORS.length];
                  return positioned.map((p) => (
                    <ScheduleRow
                      key={p.item.id}
                      positioned={p}
                      doctorColor={color}
                      doctorIndex={colorIndex}
                      totalDoctors={doctors.length}
                    />
                  ));
                })}
              </>
            ) : (
              positionedSchedules.map((positioned) => (
                <ScheduleRow
                  key={positioned.item.id}
                  positioned={positioned}
                  doctorColor={singleDoctorColor}
                />
              ))
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function ScheduleRow({
  positioned,
  doctorColor,
  doctorIndex,
  totalDoctors,
}: {
  positioned: PositionedTimelineItem<DashboardScheduleItem>;
  doctorColor?: DoctorColor;
  doctorIndex?: number;
  totalDoctors?: number;
}) {
  const { item, top, height, timeLabel, columnIndex, columnCount } = positioned;
  const typeStyle = visitTypeStyle[item.type];

  const cardColorClass = doctorColor
    ? `border-slate-200 bg-white text-slate-800 ${doctorColor.bar}`
    : typeStyle.card;

  let leftStyle: string;
  let widthStyle: string;
  if (doctorIndex !== undefined && totalDoctors !== undefined && totalDoctors > 1) {
    const zoneWidthPct = 100 / totalDoctors;
    const zoneStartPct = doctorIndex * zoneWidthPct;
    const cardLeftPct = zoneStartPct + (columnIndex / columnCount) * zoneWidthPct;
    const cardWidthPct = zoneWidthPct / columnCount;
    const gap = columnCount > 1 ? 4 : 2;
    leftStyle = `calc(${cardLeftPct}% + ${gap}px)`;
    widthStyle = `calc(${cardWidthPct}% - ${gap * 2}px)`;
  } else {
    leftStyle = `${(columnIndex / columnCount) * 100}%`;
    widthStyle = `calc(${100 / columnCount}% - ${columnCount > 1 ? 4 : 0}px)`;
  }

  return (
    <article
      className={`absolute z-10 flex items-center justify-between gap-3 overflow-hidden rounded-lg border py-2 pl-5 pr-3.5 text-left shadow-[0_4px_12px_rgba(15,23,42,0.08)] before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg ${cardColorClass}`}
      style={{
        top,
        height: Math.max(height, TIMELINE_MIN_CARD_HEIGHT),
        left: leftStyle,
        width: widthStyle,
      }}
    >
      <div className="grid min-w-0 flex-1 items-center gap-4 grid-cols-[92px_minmax(100px,1fr)]">
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
