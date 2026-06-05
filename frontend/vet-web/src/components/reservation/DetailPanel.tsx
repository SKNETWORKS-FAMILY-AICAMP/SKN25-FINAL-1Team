import { CalendarDays, Pencil, Trash2 } from "lucide-react";
import type {
  ReservationItem,
  ReservationPatient,
} from "../../types/reservation";
import { TriageBadge } from "../common/TriageBadge";
import { GenderBadge } from "../common/GenderBadge";
import {
  formatDateWithWeekday,
} from "../../utils/reservationUtils";

interface DetailPanelProps {
  selectedDate: Date;
  reservation?: ReservationItem;
  patient?: ReservationPatient;
  onEdit: () => void;
  onCancel: () => void;
}

export function DetailPanel({
  selectedDate,
  reservation,
  patient,
  onEdit,
  onCancel,
}: DetailPanelProps) {
  if (!reservation || !patient) {
    return (
      <section className="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-[#e5eaf2] bg-white p-6 shadow-sm">
        <CalendarDays className="h-10 w-10 text-[#c5cedf]" />
        <p className="text-sm font-bold text-[#778196]">예약을 선택해주세요.</p>
        <p className="text-xs text-[#a0adc0]">왼쪽 타임라인에서 예약 항목을 클릭하세요.</p>
      </section>
    );
  }

  return (
    <section className="flex h-full flex-col rounded-lg border border-[#e5eaf2] bg-white p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-base font-extrabold text-[#151b28]">예약 상세 정보</h2>
      </div>

      <div className="flex items-center gap-4">
        <img
          src={patient.imageUrl}
          alt={patient.petName}
          className="h-20 w-20 rounded-lg object-cover"
        />
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h3 className="truncate text-base font-extrabold text-[#1d2a57]">
              {patient.petName} ({patient.guardianName})
            </h3>
            <TriageBadge level={reservation.status} />
            <span className="text-xl font-extrabold text-[#2a8587]">
              <GenderBadge gender={patient.gender} className="text-xl" />
            </span>
          </div>
          <p className="mt-2 text-xs font-bold text-[#53617c]">
            {patient.breed} ㅣ {patient.age} ㅣ {patient.weight}
          </p>
          <p className="mt-2 text-sm font-extrabold text-[#1d2a57]">
            {patient.phone}
          </p>
        </div>
      </div>

      <dl className="mt-7 space-y-4 text-sm">
        <DetailRow label="예약 날짜" value={formatDateWithWeekday(selectedDate)} />
        <DetailRow label="예약 시간" value={reservation.start} />
        <DetailRow label="성별" value={patient.gender} />
        <DetailRow label="진료 항목" value={reservation.visitReason} />
        <DetailRow label="담당 수의사" value={reservation.doctorName} />
        <DetailRow label="메모" value={reservation.memo} />
      </dl>

      <div className="mt-auto grid grid-cols-2 gap-3 pt-5">
        <button
          type="button"
          onClick={onEdit}
          className="flex h-11 items-center justify-center gap-2 rounded-lg border border-[#2a8587] text-sm font-extrabold text-[#2a8587]"
        >
          <Pencil className="h-4 w-4" />
          수정
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="flex h-11 items-center justify-center gap-2 rounded-lg border border-[#e06666] text-sm font-extrabold text-[#e06666]"
        >
          <Trash2 className="h-4 w-4" />
          삭제
        </button>
      </div>
    </section>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[96px_1fr] gap-3 border-b border-[#edf1f6] pb-3">
      <dt className="font-extrabold text-[#53617c]">{label}</dt>
      <dd className="font-extrabold text-[#1d2a57]">{value}</dd>
    </div>
  );
}
