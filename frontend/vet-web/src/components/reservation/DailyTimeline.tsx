import { useMemo } from "react";
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
  TIMELINE_MIN_CARD_HEIGHT,
  type PositionedTimelineItem,
  buildPositionedTimelineItems,
  getHourTicks,
  getLunchBlockMetrics,
  getTimelineHeight,
  getTimelineRange,
} from "../../utils/scheduleTimelineUtils";

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
  const timelineRange = useMemo(
    () => getTimelineRange(reservations),
    [reservations]
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
  const positionedReservations = useMemo(
    () => buildPositionedTimelineItems(reservations, timelineRange),
    [reservations, timelineRange]
  );

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-lg border border-[#e5eaf2] bg-white p-3 shadow-sm">
      <div className="mb-1.5 shrink-0 text-center">
        <p className="text-base font-extrabold text-[#151b28]">
          {dayLabels[selectedDate.getDay()]}요일
        </p>
        <p className="text-sm font-extrabold text-[#1d2a57]">
          {selectedDate.getMonth() + 1}/{selectedDate.getDate()}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <div className="grid grid-cols-[56px_1fr] gap-2">
          <div className="relative" style={{ height: timelineHeight }}>
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 text-sm font-extrabold tabular-nums text-[#1d2a57]"
                style={{ top: tick.top }}
              >
                {tick.label}
              </div>
            ))}
          </div>

          <div
            className="relative overflow-hidden rounded-lg border border-[#edf1f6] bg-white"
            style={{ height: timelineHeight }}
          >
            {hourTicks.map((tick) => (
              <div
                key={tick.minutes}
                className="absolute left-0 right-0 border-t border-[#edf1f6]"
                style={{ top: tick.top }}
              />
            ))}

            <div
              className="absolute left-1.5 right-1.5 flex items-center gap-5 rounded-md border border-[#e7ebf2] bg-[#f1f3f7] px-3 text-xs font-extrabold text-[#53617c]"
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

  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className={[
        `absolute z-10 flex items-center gap-3 overflow-hidden rounded-lg border py-2 pl-5 pr-3.5 text-left transition before:absolute before:bottom-0 before:left-0 before:top-0 before:w-1.5 before:rounded-l-lg ${weeklyCardClass[item.status]}`,
        isSelected
          ? "shadow-[0_0_0_2px_rgba(15,98,254,0.12)]"
          : "shadow-sm hover:border-[#9fc0fb]",
      ].join(" ")}
      style={{
        top,
        height: Math.max(height, TIMELINE_MIN_CARD_HEIGHT),
        left: `${(columnIndex / columnCount) * 100}%`,
        width: `calc(${100 / columnCount}% - ${columnCount > 1 ? 4 : 0}px)`,
      }}
    >
      {patient && !compact && (
        <img
          src={patient.imageUrl}
          alt={patient.petName}
          className="h-9 w-9 rounded-md object-cover"
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-xs font-extrabold tabular-nums text-[#1d2a57]">
          {timeLabel}
        </p>
        <p className="truncate text-[15px] font-extrabold text-[#1d2a57]">
          {patient
            ? `${patient.petName} (${patient.guardianName})`
            : item.visitReason}
        </p>
      </div>
      {!compact && (
        <TriageBadge level={item.status} />
      )}
    </button>
  );
}
