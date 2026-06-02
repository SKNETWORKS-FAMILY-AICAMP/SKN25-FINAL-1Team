import { useMemo } from "react";
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
  TIMELINE_MIN_CARD_HEIGHT,
  type PositionedTimelineItem,
  buildPositionedTimelineItems,
  getHourTicks,
  getLunchBlockMetrics,
  getTimelineHeight,
  getTimelineRange,
} from "../../utils/scheduleTimelineUtils";

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
  const weekDays = useMemo(() => getWeekDays(selectedDate), [selectedDate]);
  const weekDayKeys = useMemo(
    () => new Set(weekDays.map((day) => getDateKey(day))),
    [weekDays]
  );
  const weekReservations = useMemo(
    () => reservations.filter((reservation) => weekDayKeys.has(reservation.date)),
    [reservations, weekDayKeys]
  );
  const timelineRange = useMemo(
    () => getTimelineRange(weekReservations),
    [weekReservations]
  );
  const hourTicks = useMemo(() => getHourTicks(timelineRange), [timelineRange]);
  const timelineHeight = useMemo(
    () => getTimelineHeight(timelineRange),
    [timelineRange]
  );
  const lunchBlock = useMemo(
    () => getLunchBlockMetrics(timelineRange),
    [timelineRange]
  );

  return (
    <div className="min-w-0">
      <section className="overflow-hidden rounded-lg border border-[#e5eaf2] bg-white shadow-sm">
        <div className="grid grid-cols-[62px_repeat(7,minmax(0,1fr))] border-b border-[#e5eaf2]">
          <div className="border-r border-[#e5eaf2] bg-white" />
          {weekDays.map((day, index) => {
            const isToday = isSameDate(day, TODAY);
            const isSunday = day.getDay() === 0;

            return (
              <div
                key={day.toISOString()}
                className={[
                  "flex h-12 min-w-0 flex-col items-center justify-center gap-0.5 border-r border-[#e5eaf2] px-1 text-center font-extrabold last:border-r-0",
                  isSunday ? "text-[#ef4444]" : "text-[#1d2a57]",
                ].join(" ")}
              >
                <span className="text-[11px] leading-none text-[#7a8498]">
                  {weekDayLabels[index]}
                </span>
                <span className="text-sm leading-none">
                  {String(day.getMonth() + 1).padStart(2, "0")}.
                  {String(day.getDate()).padStart(2, "0")}
                </span>
                {isToday && (
                  <span className="mt-0.5 rounded-full bg-[#2563eb] px-1.5 py-0.5 text-[10px] leading-none text-white">
                    오늘
                  </span>
                )}
              </div>
            );
          })}
        </div>

        <div
          className="relative grid grid-cols-[62px_repeat(7,minmax(0,1fr))]"
          style={{ height: timelineHeight }}
        >
          <div className="relative border-r border-[#e5eaf2]">
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 right-0 border-t border-[#edf1f6] px-2 pt-1.5 text-xs font-extrabold text-[#1d2a57]"
                style={{ top: tick.top }}
              >
                {tick.label}
              </div>
            ))}
          </div>

          <div
            className="pointer-events-none absolute right-0 z-0 flex items-center justify-center rounded-md bg-[#f1f3f7] text-xs font-extrabold text-[#53617c]"
            style={{
              left: 62,
              top: lunchBlock.top,
              height: lunchBlock.height,
            }}
          >
            점심시간
          </div>

          {weekDays.map((day) => {
            const dayKey = getDateKey(day);
            const dayReservations = reservations.filter(
              (reservation) => reservation.date === dayKey
            );
            const positionedReservations = buildPositionedTimelineItems(
              dayReservations,
              timelineRange
            );

            return (
              <div
                key={day.toISOString()}
                className="relative min-w-0 border-r border-[#edf1f6] last:border-r-0"
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
        </div>
      </section>

      <Legend />
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
  const compact = height < 58;
  const shortTimeLabel = timeLabel.replace(" ~ ", "-");

  return (
    <button
      type="button"
      onClick={() => onSelectReservation(item, day)}
      title={`${timeLabel} ${
        patient ? `${patient.petName} (${patient.guardianName})` : item.visitReason
      }`}
      className={`absolute z-10 overflow-hidden rounded-lg border py-2 pl-3.5 pr-2.5 text-left shadow-sm transition before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1 before:rounded-l-lg hover:-translate-y-0.5 hover:shadow-md ${weeklyCardClass[item.status]}`}
      style={{
        top,
        height: Math.max(height, TIMELINE_MIN_CARD_HEIGHT),
        left: `calc(${(columnIndex / columnCount) * 100}% + 5px)`,
        width: `calc(${100 / columnCount}% - ${columnCount > 1 ? 10 : 10}px)`,
      }}
    >
      <p className="whitespace-nowrap text-[11px] font-extrabold leading-tight tabular-nums text-[#40506a]">
        {shortTimeLabel}
      </p>
      <p className="mt-0.5 break-keep text-[13px] font-extrabold leading-tight text-[#20283a]">
        {patient ? patient.petName : item.visitReason}
        {patient && !compact ? (
          <span className="ml-1 text-[11px] font-bold text-[#647086]">
            {patient.guardianName}
          </span>
        ) : null}
      </p>
      {!compact && (
        <>
          <p className="mt-1 truncate text-[11px] font-bold text-[#647086]">
            {item.visitReason}
          </p>
          <span className="absolute bottom-1.5 right-1.5">
            <TriageBadge level={item.status} />
          </span>
        </>
      )}
    </button>
  );
}

function Legend() {
  const items: Array<{ label: string; className: string }> = [
    { label: "응급", className: "bg-[#ef6f86]" },
    { label: "준응급", className: "bg-[#f3a64a]" },
    { label: "일반", className: "bg-[#6fa989]" },
    { label: "예약 없음", className: "bg-[#d8dde6]" },
  ];

  return (
    <div className="mx-auto mt-3 flex w-fit max-w-full flex-wrap items-center justify-center gap-x-6 gap-y-2 rounded-lg border border-[#e5eaf2] bg-white px-5 py-2 shadow-sm">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-2 text-sm font-extrabold text-[#53617c]"
        >
          <span className={`h-3 w-3 rounded-full ${item.className}`} />
          {item.label}
        </div>
      ))}
    </div>
  );
}
