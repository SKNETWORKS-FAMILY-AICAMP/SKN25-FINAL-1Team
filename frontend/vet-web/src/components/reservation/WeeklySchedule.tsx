import { useEffect, useMemo, useRef, useState } from "react";
import type { DoctorInfo } from "../../api/emrApi";
import type {
  PatientsById,
  ReservationItem,
} from "../../types/reservation";
import { useClosedDates, useWeeklySchedule } from "../../contexts/OperatingHoursContext";
import type { DaySchedule } from "../../api/settingsApi";
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
  type TimelineRange,
  buildPositionedTimelineItems,
  getHourTicks,
  getLunchBlockMetrics,
  getScaledTimelineHeight,
  getTimelineHeight,
  getTimelineRange,
  parseTimeToMinutes,
  formatMinutesAsTime,
} from "../../utils/scheduleTimelineUtils";

const WEEKLY_BOTTOM_PADDING = 8;
const WEEKLY_FULL_CARD_HEIGHT = 58;
const WEEKLY_CARD_INSET = 0;

const DOCTOR_COLORS = [
  { bar: "before:bg-teal-500", dot: "bg-teal-500" },
  { bar: "before:bg-orange-300", dot: "bg-orange-300" },
  { bar: "before:bg-indigo-400", dot: "bg-indigo-400" },
  { bar: "before:bg-amber-400", dot: "bg-amber-400" },
] as const;

type DoctorColor = (typeof DOCTOR_COLORS)[number];

interface WeeklyScheduleProps {
  selectedDate: Date;
  reservations: ReservationItem[];
  patientsById: PatientsById;
  onSelectReservation: (reservation: ReservationItem, reservationDate: Date) => void;
  doctors?: DoctorInfo[];
  selectedDoctorId?: number | null;
}

function getNonOpOverlays(
  dayEntry: DaySchedule | undefined,
  range: TimelineRange,
  hourHeight: number,
): Array<{ top: number; height: number }> {
  const total = ((range.endMinutes - range.startMinutes) / 60) * hourHeight;
  if (!dayEntry?.is_open || !dayEntry.start_time || !dayEntry.end_time)
    return [{ top: 0, height: total }];

  const overlays: Array<{ top: number; height: number }> = [];
  const s = parseTimeToMinutes(dayEntry.start_time);
  const e = parseTimeToMinutes(dayEntry.end_time);
  if (s > range.startMinutes)
    overlays.push({ top: 0, height: ((s - range.startMinutes) / 60) * hourHeight });
  if (e < range.endMinutes)
    overlays.push({
      top: ((e - range.startMinutes) / 60) * hourHeight,
      height: ((range.endMinutes - e) / 60) * hourHeight,
    });
  return overlays;
}

export function WeeklySchedule({
  selectedDate,
  reservations,
  patientsById,
  onSelectReservation,
  doctors = [],
  selectedDoctorId = null,
}: WeeklyScheduleProps) {
  const weeklySchedule = useWeeklySchedule();
  const closedDates = useClosedDates();
  const timelineBodyRef = useRef<HTMLDivElement>(null);
  const [timelineBodyHeight, setTimelineBodyHeight] = useState(0);
  const weekDays = useMemo(() => getWeekDays(selectedDate), [selectedDate]);
  const weekDayKeys = useMemo(
    () => new Set(weekDays.map((day) => getDateKey(day))),
    [weekDays]
  );

  const isSplitMode = selectedDoctorId === null && doctors.length > 1;

  const singleDoctorColor = useMemo(() => {
    if (isSplitMode || selectedDoctorId === null) return undefined;
    const idx = doctors.findIndex((d) => d.doctorid === selectedDoctorId);
    if (idx === -1) return undefined;
    return DOCTOR_COLORS[idx % DOCTOR_COLORS.length];
  }, [isSplitMode, selectedDoctorId, doctors]);

  const getDayEntry = (date: Date): DaySchedule | undefined => {
    if (closedDates.has(getDateKey(date))) return undefined;
    const dow = (date.getDay() + 6) % 7;
    return weeklySchedule.find((d) => d.day_of_week === dow);
  };

  const globalRange = useMemo((): TimelineRange => {
    const openDays = weekDays
      .map(getDayEntry)
      .filter((d): d is DaySchedule => !!d?.is_open && !!d.start_time && !!d.end_time);
    if (openDays.length === 0) return { startMinutes: 9 * 60, endMinutes: 18 * 60 };
    return {
      startMinutes: Math.floor(Math.min(...openDays.map((d) => parseTimeToMinutes(d.start_time!))) / 60) * 60,
      endMinutes:   Math.ceil( Math.max(...openDays.map((d) => parseTimeToMinutes(d.end_time!)))   / 60) * 60,
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekDays, weeklySchedule, closedDates]);

  const firstOpenDay = weekDays.map(getDayEntry).find((d) => d?.is_open && d.start_time);
  const lunchStart = firstOpenDay?.lunch_start ?? "12:00";
  const lunchEnd   = firstOpenDay?.lunch_end   ?? "13:00";

  const weekReservations = useMemo(
    () =>
      reservations.filter(
        (reservation) =>
          weekDayKeys.has(reservation.date) && reservation.start !== "12:00"
      ),
    [reservations, weekDayKeys]
  );
  const timelineRange = useMemo(
    () => getTimelineRange(weekReservations, {
      startTime: formatMinutesAsTime(globalRange.startMinutes),
      endTime:   formatMinutesAsTime(globalRange.endMinutes),
      lunchStart,
      lunchEnd,
    }),
    [weekReservations, globalRange, lunchStart, lunchEnd]
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
    () => getLunchBlockMetrics(timelineRange, { ...timelineScale, lunchStart, lunchEnd }),
    [timelineRange, timelineScale, lunchStart, lunchEnd]
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
      <section className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {/* 헤더: 날짜 행 */}
        <div className="grid shrink-0 grid-cols-[62px_repeat(7,minmax(0,1fr))] border-b border-slate-200">
          {/* 왼쪽 62px: split 모드면 범례 */}
          <div className="border-r border-slate-200 bg-white">
            {isSplitMode && (
              <div className="flex h-full flex-col items-start justify-center gap-1 px-2">
                {doctors.map((doctor, i) => {
                  const color = DOCTOR_COLORS[i % DOCTOR_COLORS.length];
                  return (
                    <div key={doctor.doctorid} className="flex items-center gap-1">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${color.dot}`} />
                      <span className="truncate text-[10px] font-bold text-slate-500">
                        {doctor.doctor_name}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          {weekDays.map((day, index) => {
            const isToday = isSameDate(day, TODAY);
            const isSunday = day.getDay() === 0;

            return (
              <div
                key={day.toISOString()}
                className={[
                  "flex h-12 min-w-0 flex-col items-center justify-center gap-0.5 border-r border-slate-200 px-1 text-center font-extrabold last:border-r-0",
                  isToday ? "bg-slate-50" : "bg-white",
                  isSunday ? "text-red-500" : "text-slate-800",
                ].join(" ")}
              >
                <span
                  className={[
                    "text-[11px] leading-none",
                    isToday ? "text-blue-600" : "text-slate-500",
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
            <div className="relative border-r border-slate-200">
              {hourTicks.map((tick) => (
                <div
                  key={tick.minutes}
                  className="absolute left-0 right-0 border-t border-slate-100 px-2 pt-1 text-[11px] font-extrabold text-slate-800"
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
              const overlays = getNonOpOverlays(getDayEntry(day), timelineRange, weeklyHourHeight);

              if (isSplitMode) {
                const perDoctorPositioned = doctors.map((doctor, colorIndex) => ({
                  doctor,
                  colorIndex,
                  positioned: buildPositionedTimelineItems(
                    dayReservations.filter((r) => r.doctorid === doctor.doctorid),
                    timelineRange,
                    timelineScale,
                  ),
                }));

                return (
                  <div
                    key={day.toISOString()}
                    className={[
                      "relative min-w-0 border-r border-slate-100 last:border-r-0",
                      isToday ? "bg-slate-50" : "bg-white",
                    ].join(" ")}
                  >
                    {hourTicks.map((tick) => (
                      <div
                        key={tick.minutes}
                        className="absolute left-0 right-0 border-t border-slate-100"
                        style={{ top: tick.top }}
                      />
                    ))}

                    {/* 수의사 구분 세로선 */}
                    {doctors.slice(0, -1).map((_, i) => (
                      <div
                        key={i}
                        className="absolute top-0 bottom-0 z-[3] border-l border-slate-100"
                        style={{ left: `${((i + 1) / doctors.length) * 100}%` }}
                      />
                    ))}

                    {overlays.map((o, i) => (
                      <div
                        key={i}
                        className="pointer-events-none absolute inset-x-0 z-[2]"
                        style={{
                          top: o.top,
                          height: o.height,
                          backgroundColor: "rgba(226,232,240,0.65)",
                        }}
                      />
                    ))}

                    {perDoctorPositioned.map(({ colorIndex, positioned }) => {
                      const color = DOCTOR_COLORS[colorIndex % DOCTOR_COLORS.length];
                      return positioned.map((p) => (
                        <WeeklyReservationCard
                          key={p.item.id}
                          positioned={p}
                          patient={patientsById[p.item.patientId]}
                          day={day}
                          onSelectReservation={onSelectReservation}
                          doctorColor={color}
                          doctorIndex={colorIndex}
                          totalDoctors={doctors.length}
                        />
                      ));
                    })}
                  </div>
                );
              }

              const positionedReservations = buildPositionedTimelineItems(
                dayReservations,
                timelineRange,
                timelineScale
              );

              return (
                <div
                  key={day.toISOString()}
                  className={[
                    "relative min-w-0 border-r border-slate-100 last:border-r-0",
                    isToday ? "bg-slate-50" : "bg-white",
                  ].join(" ")}
                >
                  {hourTicks.map((tick) => (
                    <div
                      key={tick.minutes}
                      className="absolute left-0 right-0 border-t border-slate-100"
                      style={{ top: tick.top }}
                    />
                  ))}

                  {overlays.map((o, i) => (
                    <div
                      key={i}
                      className="pointer-events-none absolute inset-x-0 z-[2]"
                      style={{
                        top: o.top,
                        height: o.height,
                        backgroundColor: "rgba(226,232,240,0.65)",
                      }}
                    />
                  ))}

                  {positionedReservations.map((positioned) => (
                    <WeeklyReservationCard
                      key={positioned.item.id}
                      positioned={positioned}
                      patient={patientsById[positioned.item.patientId]}
                      day={day}
                      onSelectReservation={onSelectReservation}
                      doctorColor={singleDoctorColor}
                    />
                  ))}
                </div>
              );
            })}

            <div
              className="pointer-events-none absolute right-0 z-[1] flex items-center justify-center bg-slate-100 text-xs font-extrabold text-slate-600"
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
  doctorColor,
  doctorIndex,
  totalDoctors,
}: {
  positioned: PositionedTimelineItem<ReservationItem>;
  patient: PatientsById[number] | undefined;
  day: Date;
  onSelectReservation: (reservation: ReservationItem, reservationDate: Date) => void;
  doctorColor?: DoctorColor;
  doctorIndex?: number;
  totalDoctors?: number;
}) {
  const { item, top, height, timeLabel, columnIndex, columnCount } = positioned;
  const compact = height < WEEKLY_FULL_CARD_HEIGHT;
  const shortTimeLabel = timeLabel.replace(" ~ ", "-");

  const cardColorClass = doctorColor
    ? `bg-white border-slate-200 text-slate-800 ${doctorColor.bar}`
    : weeklyCardClass[item.status];

  let leftStyle: string;
  let widthStyle: string;
  if (doctorIndex !== undefined && totalDoctors !== undefined && totalDoctors > 1) {
    const zoneWidthPct = 100 / totalDoctors;
    const zoneStartPct = doctorIndex * zoneWidthPct;
    const cardLeftPct = zoneStartPct + (columnIndex / columnCount) * zoneWidthPct;
    const cardWidthPct = zoneWidthPct / columnCount;
    const gap = columnCount > 1 ? 2 : 1;
    leftStyle = `calc(${cardLeftPct}% + ${gap}px)`;
    widthStyle = `calc(${cardWidthPct}% - ${gap * 2}px)`;
  } else {
    leftStyle = `calc(${(columnIndex / columnCount) * 100}% + ${WEEKLY_CARD_INSET}px)`;
    widthStyle = `calc(${100 / columnCount}% - ${WEEKLY_CARD_INSET * 2}px)`;
  }

  return (
    <button
      type="button"
      onClick={() => onSelectReservation(item, day)}
      title={`${timeLabel} ${
        patient ? `${patient.petName} (${patient.guardianName})` : item.visitReason
      }`}
      className={[
        `absolute z-10 flex flex-col overflow-hidden rounded-lg border pl-3 pr-2 text-left shadow-sm transition before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1 before:rounded-l-lg hover:shadow-md ${cardColorClass}`,
        compact ? "py-1" : "py-1.5",
      ].join(" ")}
      style={{
        top,
        height,
        left: leftStyle,
        width: widthStyle,
      }}
    >
      {compact ? (
        <div className="flex min-h-0 min-w-0 flex-1 items-center gap-1.5">
          <div className="min-w-0">
            <p className="min-w-0 truncate text-[10px] font-extrabold leading-tight tabular-nums text-slate-700">
              {shortTimeLabel}
            </p>
            <p className="mt-0.5 truncate text-xs font-extrabold leading-tight text-slate-800">
              {patient ? patient.petName : item.visitReason}
            </p>
          </div>
        </div>
      ) : (
        <>
          <p className="truncate text-[10px] font-extrabold leading-tight tabular-nums text-slate-700">
            {shortTimeLabel}
          </p>
          <p className="mt-0.5 truncate text-xs font-extrabold leading-tight text-slate-800">
            {patient ? patient.petName : item.visitReason}
            {patient ? (
              <span className="ml-1 text-[10px] font-bold text-slate-500">
                {patient.guardianName}
              </span>
            ) : null}
          </p>
          {!doctorColor && (
            <p className="mt-0.5 min-w-0 truncate text-[10px] font-bold leading-tight text-slate-500">
              {item.visitReason}
            </p>
          )}
        </>
      )}
    </button>
  );
}
