import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PatientsById,
  ReservationItem,
} from "../../types/reservation";
import { TriageBadge } from "../common/TriageBadge";
import {
  TODAY,
  getDateKey,
  getWeekDays,
  isSameDate,
  weekDayLabels,
  weeklyCardClass,
} from "../../utils/reservationUtils";
import {
  TIMELINE_HOUR_HEIGHT,
  type PositionedTimelineItem,
  buildPositionedTimelineItems,
  getHourTicks,
  getLunchBlockMetrics,
  getScaledTimelineHeight,
  getTimelineHeight,
  getTimelineRange,
} from "../../utils/scheduleTimelineUtils";

const WEEKLY_BOTTOM_PADDING = 8;
const WEEKLY_FULL_CARD_HEIGHT = 58;
const WEEKLY_CARD_INSET = 4;

interface WeeklyScheduleProps {
  selectedDate: Date;
  reservations: ReservationItem[];
  patientsById: PatientsById;
  onSelectReservation: (reservation: ReservationItem, reservationDate: Date) => void;
}

export function WeeklySchedule({
  selectedDate,
  reservations,
  patientsById,
  onSelectReservation,
}: WeeklyScheduleProps) {
  const timelineBodyRef = useRef<HTMLDivElement>(null);
  const [timelineBodyHeight, setTimelineBodyHeight] = useState(0);
  const weekDays = useMemo(() => getWeekDays(selectedDate), [selectedDate]);
  const weekDayKeys = useMemo(
    () => new Set(weekDays.map((day) => getDateKey(day))),
    [weekDays]
  );
  const weekReservations = useMemo(
    () =>
      reservations.filter(
        (reservation) =>
          weekDayKeys.has(reservation.date) && reservation.start !== "12:00"
      ),
    [reservations, weekDayKeys]
  );
  const timelineRange = useMemo(
    () => getTimelineRange(weekReservations),
    [weekReservations]
  );
  const fallbackTimelineHeight = useMemo(
    () => getTimelineHeight(timelineRange),
    [timelineRange]
  );
  const timelineHourCount =
    (timelineRange.endMinutes - timelineRange.startMinutes) / 60;
  const weeklyHourHeight =
    timelineBodyHeight > WEEKLY_BOTTOM_PADDING && timelineHourCount > 0
      ? (timelineBodyHeight - WEEKLY_BOTTOM_PADDING) / timelineHourCount
      : TIMELINE_HOUR_HEIGHT;
  const timelineScale = useMemo(
    () => ({
      bottomPadding: WEEKLY_BOTTOM_PADDING,
      hourHeight: weeklyHourHeight,
    }),
    [weeklyHourHeight]
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

  useEffect(() => {
    const element = timelineBodyRef.current;

    if (!element) {
      return;
    }

    const updateHeight = () => {
      setTimelineBodyHeight(element.clientHeight);
    };
    updateHeight();

    const observer = new ResizeObserver(updateHeight);
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  return (
    <div className="h-full min-w-0">
      <section className="flex h-full flex-col overflow-hidden rounded-lg border border-[#e5eaf2] bg-white shadow-sm">
        <div className="grid shrink-0 grid-cols-[62px_repeat(7,minmax(0,1fr))] border-b border-[#e5eaf2]">
          <div className="border-r border-[#e5eaf2] bg-white" />
          {weekDays.map((day, index) => {
            const isToday = isSameDate(day, TODAY);
            const isSunday = day.getDay() === 0;

            return (
              <div
                key={day.toISOString()}
                className={[
                  "flex h-12 min-w-0 flex-col items-center justify-center gap-0.5 border-r border-[#e5eaf2] px-1 text-center font-extrabold last:border-r-0",
                  isToday ? "bg-[#f9fbfc]" : "bg-white",
                  isSunday ? "text-[#ef4444]" : "text-[#1d2a57]",
                ].join(" ")}
              >
                <span
                  className={[
                    "text-[11px] leading-none",
                    isToday ? "text-[#2f6f67]" : "text-[#7a8498]",
                  ].join(" ")}
                >
                  {weekDayLabels[index]}
                </span>
                <span className="text-sm leading-none">
                  {String(day.getMonth() + 1).padStart(2, "0")}.
                  {String(day.getDate()).padStart(2, "0")}
                </span>
              </div>
            );
          })}
        </div>

        <div ref={timelineBodyRef} className="min-h-0 flex-1 overflow-hidden">
          <div
            className="relative grid grid-cols-[62px_repeat(7,minmax(0,1fr))]"
            style={{
              height:
                timelineBodyHeight > 0 ? timelineHeight : fallbackTimelineHeight,
            }}
          >
            <div className="relative border-r border-[#e5eaf2]">
              {hourTicks.map((tick) => (
                <div
                  key={tick.minutes}
                  className="absolute left-0 right-0 border-t border-[#edf1f6] px-2 pt-1 text-[11px] font-extrabold text-[#1d2a57]"
                  style={{ top: tick.top }}
                >
                  {tick.label}
                </div>
              ))}
            </div>

            {weekDays.map((day) => {
              const isToday = isSameDate(day, TODAY);
              const dayKey = getDateKey(day);
              const dayReservations = reservations.filter(
                (reservation) =>
                  reservation.date === dayKey && reservation.start !== "12:00"
              );
              const positionedReservations = buildPositionedTimelineItems(
                dayReservations,
                timelineRange,
                timelineScale
              );

              return (
                <div
                  key={day.toISOString()}
                  className={[
                    "relative min-w-0 border-r border-[#edf1f6] last:border-r-0",
                    isToday ? "bg-[#fbfcfc]" : "bg-white",
                  ].join(" ")}
                >
                  {hourTicks.map((tick) => (
                    <div
                      key={tick.minutes}
                      className="absolute left-0 right-0 border-t border-[#edf1f6]"
                      style={{ top: tick.top }}
                    />
                  ))}

                  {positionedReservations.map((positioned) => (
                    <WeeklyReservationCard
                      key={positioned.item.id}
                      positioned={positioned}
                      patient={patientsById[positioned.item.patientId]}
                      day={day}
                      onSelectReservation={onSelectReservation}
                    />
                  ))}
                </div>
              );
            })}

            <div
              className="pointer-events-none absolute right-0 z-[1] flex items-center justify-center bg-[#f1f3f7] text-xs font-extrabold text-[#53617c]"
              style={{
                left: 62,
                top: lunchBlock.top,
                height: lunchBlock.height,
              }}
            >
              점심시간
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function WeeklyReservationCard({
  positioned,
  patient,
  day,
  onSelectReservation,
}: {
  positioned: PositionedTimelineItem<ReservationItem>;
  patient: PatientsById[number] | undefined;
  day: Date;
  onSelectReservation: (reservation: ReservationItem, reservationDate: Date) => void;
}) {
  const { item, top, height, timeLabel, columnIndex, columnCount } = positioned;
  const compact = height < WEEKLY_FULL_CARD_HEIGHT;
  const shortTimeLabel = timeLabel.replace(" ~ ", "-");

  return (
    <button
      type="button"
      onClick={() => onSelectReservation(item, day)}
      title={`${timeLabel} ${
        patient ? `${patient.petName} (${patient.guardianName})` : item.visitReason
      }`}
      className={[
        `absolute z-10 flex flex-col overflow-hidden rounded-lg border pl-3 pr-2 text-left shadow-sm transition before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1 before:rounded-l-lg hover:shadow-md ${weeklyCardClass[item.status]}`,
        compact ? "py-1" : "py-1.5",
      ].join(" ")}
      style={{
        top,
        height,
        left: `calc(${(columnIndex / columnCount) * 100}% + ${WEEKLY_CARD_INSET}px)`,
        width: `calc(${100 / columnCount}% - ${WEEKLY_CARD_INSET * 2}px)`,
      }}
    >
      {compact ? (
        <div className="flex min-h-0 min-w-0 flex-1 items-center justify-between gap-1.5">
          <div className="min-w-0">
            <p className="min-w-0 truncate text-[10px] font-extrabold leading-tight tabular-nums text-[#40506a]">
              {shortTimeLabel}
            </p>
            <p className="mt-0.5 truncate text-xs font-extrabold leading-tight text-[#20283a]">
              {patient ? patient.petName : item.visitReason}
            </p>
          </div>
          <span className="shrink-0">
            <TriageBadge level={item.status} />
          </span>
        </div>
      ) : (
        <>
          <p className="truncate text-[10px] font-extrabold leading-tight tabular-nums text-[#40506a]">
            {shortTimeLabel}
          </p>
          <p className="mt-0.5 truncate text-xs font-extrabold leading-tight text-[#20283a]">
            {patient ? patient.petName : item.visitReason}
            {patient ? (
              <span className="ml-1 text-[10px] font-bold text-[#647086]">
                {patient.guardianName}
              </span>
            ) : null}
          </p>
          <div className="mt-0.5 flex h-5 min-w-0 items-center justify-between gap-1 overflow-hidden">
            <p className="min-w-0 truncate text-[10px] font-bold leading-tight text-[#647086]">
              {item.visitReason}
            </p>
            <span className="shrink-0">
              <TriageBadge level={item.status} />
            </span>
          </div>
        </>
      )}
    </button>
  );
}
