import type { ReservationStatus } from "../../types/reservation";
import {
  reservationStatusMeta,
  statusOrder,
} from "../../utils/reservationUtils";

interface StatusFilterProps {
  counts: Record<ReservationStatus, number>;
  activeStatus: ReservationStatus | null;
  onChangeStatus: (status: ReservationStatus | null) => void;
}

export function StatusFilter({
  counts,
  activeStatus,
  onChangeStatus,
}: StatusFilterProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="text-sm font-extrabold text-slate-900">상태 필터</h2>
        {activeStatus && (
          <button
            type="button"
            onClick={() => onChangeStatus(null)}
            className="rounded-md border border-slate-200 px-2 py-1 text-xs font-extrabold text-slate-600"
          >
            전체
          </button>
        )}
      </div>
      <div className="space-y-3">
        {statusOrder.map((status) => {
          const meta = reservationStatusMeta[status];
          const isActive = activeStatus === status;

          return (
            <button
              key={status}
              type="button"
              onClick={() => onChangeStatus(isActive ? null : status)}
              className={[
                "flex w-full items-center justify-between rounded-lg p-1.5 text-left transition",
                isActive
                  ? "bg-slate-50 ring-2 ring-blue-600/20"
                  : "hover:bg-slate-50",
              ].join(" ")}
            >
              <span
                className={`inline-flex h-9 w-[72px] items-center justify-center rounded-md text-sm font-extrabold ${meta.softClass}`}
              >
                {meta.label}
              </span>
              <span className="flex h-8 min-w-8 items-center justify-center rounded-lg border border-slate-100 bg-white px-2 text-sm font-extrabold text-slate-800">
                {counts[status] ?? 0}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
