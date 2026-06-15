import { useEffect, useMemo, useRef, useState } from "react";
import type { DoctorInfo } from "../../api/emrApi";
import type {
  PatientsById,
  ReservationItem,
} from "../../types/reservation";
import { useOperatingHoursForDate } from "../../contexts/OperatingHoursContext";
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

const DOCTOR_COLORS = [
  {
    bg: "bg-white",
    border: "border-slate-200",
    bar: "before:bg-slate-400",
    dot: "bg-slate-400",
  },
  {
    bg: "bg-white",
    border: "border-slate-200",
    bar: "before:bg-stone-400",
    dot: "bg-stone-400",
  },
  {
    bg: "bg-white",
    border: "border-slate-200",
    bar: "before:bg-amber-500",
    dot: "bg-amber-500",
  },
  {
    bg: "bg-white",
    border: "border-slate-200",
    bar: "before:bg-rose-500",
    dot: "bg-rose-500",
  },
] as const;

type DoctorColor = (typeof DOCTOR_COLORS)[number];

interface DailyTimelineProps {
  selectedDate: Date;
  reservations: ReservationItem[];
  patientsById: PatientsById;
  selectedReservationId: number;
  onSelect: (id: number) => void;
  doctors: DoctorInfo[];
  selectedDoctorId: number | null;
}

export function DailyTimeline({
  selectedDate,
  reservations,
  patientsById,
  selectedReservationId,
  onSelect,
  doctors,
  selectedDoctorId,
}: DailyTimelineProps) {
  const hoursForDate = useOperatingHoursForDate(selectedDate);
  const startTime = hoursForDate?.startTime ?? "09:00";
  const endTime = hoursForDate?.endTime ?? "18:00";
  const lunchStart = hoursForDate?.lunchStart ?? "12:00";
  const lunchEnd = hoursForDate?.lunchEnd ?? "13:00";
  const timelineBodyRef = useRef<HTMLDivElement>(null);
  const [timelineBodyHeight, setTimelineBodyHeight] = useState(0);

  const isSplitMode = selectedDoctorId === null && doctors.length > 1;

  const timelineRange = useMemo(
    () => getTimelineRange(reservations, { startTime, endTime, lunchStart, lunchEnd }),
    [reservations, startTime, endTime, lunchStart, lunchEnd]
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
    () => getLunchBlockMetrics(timelineRange, { ...timelineScale, lunchStart, lunchEnd }),
    [timelineRange, timelineScale, lunchStart, lunchEnd]
  );

  // 단일 모드용 포지셔닝
  const positionedReservations = useMemo(
    () =>
      isSplitMode
        ? []
        : buildPositionedTimelineItems(reservations, timelineRange, timelineScale),
    [isSplitMode, reservations, timelineRange, timelineScale]
  );

  // 단일 모드에서 선택된 수의사 색상
  const singleDoctorColor = useMemo(() => {
    if (isSplitMode || selectedDoctorId === null) return undefined;
    const idx = doctors.findIndex((d) => d.doctorid === selectedDoctorId);
    if (idx === -1) return undefined;
    return DOCTOR_COLORS[idx % DOCTOR_COLORS.length];
  }, [isSplitMode, selectedDoctorId, doctors]);

  // 분리 모드용: 수의사별 포지셔닝
  const perDoctorPositioned = useMemo(() => {
    if (!isSplitMode) return [];
    return doctors.map((doctor, colorIndex) => ({
      doctor,
      colorIndex,
      positioned: buildPositionedTimelineItems(
        reservations.filter((r) => r.doctorid === doctor.doctorid),
        timelineRange,
        timelineScale,
      ),
    }));
  }, [isSplitMode, doctors, reservations, timelineRange, timelineScale]);

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
    <section className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="mb-1.5 shrink-0 grid grid-cols-[1fr_auto_1fr] items-start px-1">
        <div />
        <div className="text-center">
          <p className="text-sm font-extrabold text-slate-900">
            {dayLabels[selectedDate.getDay()]}요일
          </p>
          <p className="text-xs font-bold text-slate-600">
            {selectedDate.getMonth() + 1}/{selectedDate.getDate()}
          </p>
        </div>
        {isSplitMode ? (
          <div className="flex items-center justify-end gap-3 pt-0.5">
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
        ) : (
          <div />
        )}
      </div>

      <div ref={timelineBodyRef} className="min-h-0 flex-1 overflow-hidden pr-1">
        <div
          className="grid grid-cols-[56px_1fr] gap-2"
          style={{
            height: timelineBodyHeight > 0 ? timelineHeight : fallbackTimelineHeight,
          }}
        >
          {/* 시간 레이블 */}
          <div className="relative">
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

          {isSplitMode ? (
            // 단일 컨테이너 — 세로선으로 수의사 영역 구분
            <div className="relative overflow-hidden rounded-lg border border-slate-100 bg-white">
              {/* 시간 그리드선 — 전체 너비 */}
              {hourTicks.map((tick) => (
                <div
                  key={tick.minutes}
                  className="absolute left-0 right-0 border-t border-slate-100"
                  style={{ top: tick.top }}
                />
              ))}

              {/* 점심 블록 — 전체 너비 */}
              <div
                className="absolute inset-x-0 flex items-center gap-5 bg-slate-100 px-3 text-xs font-extrabold text-slate-600"
                style={{ top: lunchBlock.top, height: lunchBlock.height }}
              >
                <span>{lunchBlock.timeLabel}</span>
                <span>점심시간</span>
              </div>

              {/* 세로 구분선 */}
              {doctors.slice(0, -1).map((_, i) => (
                <div
                  key={i}
                  className="absolute top-0 bottom-0 z-10 border-l border-slate-200"
                  style={{ left: `${((i + 1) / doctors.length) * 100}%` }}
                />
              ))}

              {/* 수의사별 예약 카드 */}
              {perDoctorPositioned.map(({ doctor, colorIndex, positioned }) => {
                const color = DOCTOR_COLORS[colorIndex % DOCTOR_COLORS.length];
                return positioned.map((p) => (
                  <ReservationCard
                    key={p.item.id}
                    positioned={p}
                    patient={patientsById[p.item.patientId]}
                    isSelected={selectedReservationId === p.item.id}
                    onSelect={onSelect}
                    doctorColor={color}
                    doctorIndex={colorIndex}
                    totalDoctors={doctors.length}
                  />
                ));
              })}
            </div>
          ) : (
            // 단일 모드: 기존과 동일
            <div className="relative overflow-hidden rounded-lg border border-slate-100 bg-white">
              {hourTicks.map((tick) => (
                <div
                  key={tick.minutes}
                  className="absolute left-0 right-0 border-t border-slate-100"
                  style={{ top: tick.top }}
                />
              ))}
              <div
                className="absolute inset-x-0 flex items-center gap-5 bg-slate-100 px-3 text-xs font-extrabold text-slate-600"
                style={{ top: lunchBlock.top, height: lunchBlock.height }}
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
                  doctorColor={singleDoctorColor}
                />
              ))}
            </div>
          )}
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
  doctorColor,
  doctorIndex,
  totalDoctors,
}: {
  positioned: PositionedTimelineItem<ReservationItem>;
  patient: PatientsById[number] | undefined;
  isSelected: boolean;
  onSelect: (id: number) => void;
  doctorColor?: DoctorColor;
  doctorIndex?: number;
  totalDoctors?: number;
}) {
  const { item, top, height, timeLabel, columnIndex, columnCount } = positioned;
  const compact = height < 54;
  const imageSizeClass = compact ? "h-7 w-7" : "h-8 w-8";

  const cardColorClass = doctorColor
    ? `${doctorColor.bg} ${doctorColor.border} ${doctorColor.bar}`
    : weeklyCardClass[item.status];

  // 분리 모드: 수의사 영역 내에서 카드 위치 계산
  let leftStyle: string;
  let widthStyle: string;
  if (doctorIndex !== undefined && totalDoctors !== undefined && totalDoctors > 1) {
    const zoneWidthPct = 100 / totalDoctors;
    const zoneStartPct = doctorIndex * zoneWidthPct;
    const cardLeftPct = zoneStartPct + (columnIndex / columnCount) * zoneWidthPct;
    const cardWidthPct = zoneWidthPct / columnCount;
    const gap = columnCount > 1 ? 4 : 0;
    leftStyle = `${cardLeftPct}%`;
    widthStyle = `calc(${cardWidthPct}% - ${gap}px)`;
  } else {
    leftStyle = `${(columnIndex / columnCount) * 100}%`;
    widthStyle = `calc(${100 / columnCount}% - ${columnCount > 1 ? 4 : 0}px)`;
  }

  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className={[
        `absolute z-10 flex items-center overflow-hidden rounded-lg border pl-4 pr-3 text-left transition before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg ${cardColorClass}`,
        compact ? "gap-2 py-1.5" : "gap-2.5 py-2",
        isSelected
          ? "z-20 border-blue-600 bg-blue-50 shadow-[0_0_0_1px_#7fb1a8]"
          : "shadow-sm hover:border-blue-200",
      ].join(" ")}
      style={{
        top,
        height: Math.max(height, TIMELINE_MIN_CARD_HEIGHT),
        left: leftStyle,
        width: widthStyle,
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
        <p className="text-xs font-extrabold tabular-nums text-slate-600">
          {timeLabel}
        </p>
        <p className="truncate text-sm font-extrabold text-slate-800">
          {patient
            ? `${patient.petName} (${patient.guardianName})`
            : item.visitReason}
        </p>
      </div>
      <TriageBadge level={item.status} />
    </button>
  );
}
