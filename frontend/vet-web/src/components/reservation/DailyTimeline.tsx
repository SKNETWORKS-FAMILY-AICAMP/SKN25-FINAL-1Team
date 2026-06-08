import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PatientsById,
  ReservationItem,
} from "../../types/reservation";
import { TriageBadge } from "../common/TriageBadge";
import {
  dayLabels,
  weeklyCardClass,
} from "../../utils/reservationUtils";
import {
  TIMELINE_HOUR_HEIGHT,
  TIMELINE_MIN_CARD_HEIGHT,
  type PositionedTimelineItem,
  buildPositionedTimelineItems,
  getHourTicks,
  getLunchBlockMetrics,
  getScaledTimelineHeight,
  getTimelineHeight,
  getTimelineRange,
} from "../../utils/scheduleTimelineUtils";

const DAILY_BOTTOM_PADDING = 24;

interface DailyTimelineProps {
  selectedDate: Date;
  reservations: ReservationItem[];
  patientsById: PatientsById;
  selectedReservationId: number;
  onSelect: (id: number) => void;
}

export function DailyTimeline({
  selectedDate,
  reservations,
  patientsById,
  selectedReservationId,
  onSelect,
}: DailyTimelineProps) {
  const timelineBodyRef = useRef<HTMLDivElement>(null);
  const [timelineBodyHeight, setTimelineBodyHeight] = useState(0);

  const timelineRange = useMemo(
    () => getTimelineRange(reservations),
    [reservations]
  );
  const fallbackTimelineHeight = useMemo(
    () => getTimelineHeight(timelineRange),
    [timelineRange]
  );
  const timelineHourCount =
    (timelineRange.endMinutes - timelineRange.startMinutes) / 60;
  const dailyHourHeight =
    timelineBodyHeight > DAILY_BOTTOM_PADDING && timelineHourCount > 0
      ? (timelineBodyHeight - DAILY_BOTTOM_PADDING) / timelineHourCount
      : TIMELINE_HOUR_HEIGHT;
  const timelineScale = useMemo(
    () => ({ hourHeight: dailyHourHeight, bottomPadding: DAILY_BOTTOM_PADDING }),
    [dailyHourHeight]
  );
  const hourTicks = useMemo(
    () => getHourTicks(timelineRange, timelineScale),
    [timelineRange, timelineScale]
  );
  const timelineHeight = useMemo(
    () =>
      timelineBodyHeight > 0
        ? timelineBodyHeight
        : getScaledTimelineHeight(timelineRange, timelineScale),
    [timelineBodyHeight, timelineRange, timelineScale]
  );
  const lunchBlock = useMemo(
    () => getLunchBlockMetrics(timelineRange, timelineScale),
    [timelineRange, timelineScale]
  );
  const positionedReservations = useMemo(
    () => buildPositionedTimelineItems(reservations, timelineRange, timelineScale),
    [reservations, timelineRange, timelineScale]
  );

  useEffect(() => {
    const element = timelineBodyRef.current;
    if (!element) return;
    const updateHeight = () => setTimelineBodyHeight(element.clientHeight);
    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-lg border border-[#e5eaf2] bg-white p-3 shadow-sm">
      <div className="mb-1.5 shrink-0 text-center">
        <p className="text-sm font-extrabold text-[#151b28]">
          {dayLabels[selectedDate.getDay()]}요일
        </p>
        <p className="text-xs font-bold text-[#53617c]">
          {selectedDate.getMonth() + 1}/{selectedDate.getDate()}
        </p>
      </div>

      <div ref={timelineBodyRef} className="min-h-0 flex-1 overflow-hidden pr-1">
        <div
          className="grid grid-cols-[56px_1fr] gap-2"
          style={{
            height:
              timelineBodyHeight > 0 ? timelineHeight : fallbackTimelineHeight,
          }}
        >
          <div className="relative">
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 text-xs font-extrabold tabular-nums text-[#556179]"
                style={{ top: tick.top }}
              >
                {tick.label}
              </div>
            ))}
          </div>

          <div className="relative overflow-hidden rounded-lg border border-[#edf1f6] bg-white">
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 right-0 border-t border-[#edf1f6]"
                style={{ top: tick.top }}
              />
            ))}

            <div
              className="absolute inset-x-0 flex items-center gap-5 bg-[#f1f3f7] px-3 text-xs font-extrabold text-[#53617c]"
              style={{
                top: lunchBlock.top,
                height: lunchBlock.height,
              }}
            >
              <span>{lunchBlock.timeLabel}</span>
              <span>점심시간</span>
            </div>

            {positionedReservations.map((positioned) => (
              <ReservationCard
                key={positioned.item.id}
                positioned={positioned}
                patient={patientsById[positioned.item.patientId]}
                isSelected={selectedReservationId === positioned.item.id}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function ReservationCard({
  positioned,
  patient,
  isSelected,
  onSelect,
}: {
  positioned: PositionedTimelineItem<ReservationItem>;
  patient: PatientsById[number] | undefined;
  isSelected: boolean;
  onSelect: (id: number) => void;
}) {
  const { item, top, height, timeLabel, columnIndex, columnCount } = positioned;
  const compact = height < 54;
  const imageSizeClass = compact ? "h-7 w-7" : "h-8 w-8";

  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className={[
        `absolute z-10 flex items-center overflow-hidden rounded-lg border pl-4 pr-3 text-left transition before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg ${weeklyCardClass[item.status]}`,
        compact ? "gap-2 py-1.5" : "gap-2.5 py-2",
        isSelected
          ? "z-20 border-[#2f6f67] bg-[#eef5f4] shadow-[0_0_0_1px_#7fb1a8]"
          : "shadow-sm hover:border-[#aecfc9]",
      ].join(" ")}
      style={{
        top,
        height: Math.max(height, TIMELINE_MIN_CARD_HEIGHT),
        left: `${(columnIndex / columnCount) * 100}%`,
        width: `calc(${100 / columnCount}% - ${columnCount > 1 ? 4 : 0}px)`,
      }}
    >
      {patient && (
        <img
          src={patient.imageUrl}
          alt={patient.petName}
          className={`${imageSizeClass} shrink-0 rounded-md object-cover`}
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-xs font-extrabold tabular-nums text-[#556179]">
          {timeLabel}
        </p>
        <p className="truncate text-sm font-extrabold text-[#222b3c]">
          {patient
            ? `${patient.petName} (${patient.guardianName})`
            : item.visitReason}
        </p>
      </div>
      <TriageBadge level={item.status} />
    </button>
  );
}
