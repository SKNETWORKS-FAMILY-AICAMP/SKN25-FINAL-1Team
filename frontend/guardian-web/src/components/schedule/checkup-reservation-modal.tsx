import React, { useRef } from "react";

import type { Pet } from "../../api/pets-api";
import ActionButton from "../common/action-button";
import { useCheckupReservation } from "../../hooks/use-checkup-reservation";
import { useTranslation } from "../../i18n/language-context";

interface CheckupReservationModalProps {
  pet: Pet;
  categoryCode?: number;
  onClose: () => void;
}

type PetWithOptionalName = Pet & {
  name?: string;
};

const CloseIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden="true">
    <path
      d="m6 6 12 12M18 6 6 18"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>
);

const CheckupReservationModal = ({
  pet,
  categoryCode = 1,
  onClose,
}: CheckupReservationModalProps) => {
  const { t } = useTranslation();
  const categoryLabel = categoryCode === 2 ? "일반진료" : "정기검진";
  const getPetMeta = (item: Pet) =>
    [item.breed || item.species, item.age ? t("home.yearsOld", { age: item.age }) : undefined]
      .filter(Boolean)
      .join(" · ");
  const dateInputRef = useRef<HTMLInputElement>(null);
  const {
    selectedDate,
    selectedSlot,
    memo,
    availableSlots,
    isLoadingSlots,
    isSubmitting,
    errorMessage,
    completedReservation,
    setSelectedDate,
    setSelectedSlot,
    setMemo,
    reserveCheckup,
  } = useCheckupReservation({ petId: pet.pet_id, categoryCode });
  const petDisplayName =
    completedReservation?.pet_name ?? (pet as PetWithOptionalName).name ?? pet.petname;

  const handleOpenDatePicker = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      if (dateInputRef.current) {
        if (typeof dateInputRef.current.showPicker === "function") {
          dateInputRef.current.showPicker();
        } else {
          dateInputRef.current.focus();
        }
      }
    } catch (error) {
      console.warn("showPicker failed, falling back to focus:", error);
      dateInputRef.current?.focus();
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 px-4 py-4">
      <section className="max-h-full w-full max-w-xl overflow-y-auto rounded-2xl bg-white shadow-2xl shadow-slate-900/20">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5 sm:px-6">
          <div>
            <h2 className="text-lg font-extrabold text-slate-950">
              {t("schedule.instantTitle")}
            </h2>
            <span className="mt-0.5 inline-block rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-600">
              {categoryLabel}
            </span>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-50 hover:text-slate-700"
            aria-label={t("schedule.checkupCloseAria")}
          >
            <CloseIcon />
          </button>
        </div>

        {completedReservation ? (
          <div className="px-5 py-5 sm:px-6">
            <div className="rounded-2xl bg-blue-50 px-5 py-5 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-blue-600 text-lg font-extrabold text-white">
                ✓
              </div>
              <h3 className="mt-3 text-xl font-extrabold text-slate-950">
                {t("schedule.completeTitle")}
              </h3>
              <p className="mt-2 text-sm font-semibold text-slate-500">
                {t("schedule.completeDesc")}
              </p>
            </div>

            <dl className="mt-4 divide-y divide-slate-100 rounded-2xl border border-slate-100 px-4">
              {[
                [t("schedule.fieldPet"), petDisplayName],
                [t("schedule.fieldDate"), completedReservation.date],
                [
                  t("schedule.fieldTime"),
                  `${completedReservation.time} - ${completedReservation.end_time}`,
                ],
                [t("schedule.fieldMemo"), completedReservation.memo || t("schedule.memoNone")],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="grid grid-cols-[92px_1fr] gap-4 py-3 text-sm"
                >
                  <dt className="font-extrabold text-slate-500">{label}</dt>
                  <dd className="font-bold text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>

            <div className="mt-5 flex justify-end">
              <ActionButton type="button" onClick={onClose} size="lg">
                {t("schedule.goHome")}
              </ActionButton>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              reserveCheckup();
            }}
          >
            <div className="space-y-4 px-5 py-4 sm:px-6">
              <div className="rounded-xl bg-slate-50 px-4 py-3">
                <p className="truncate text-base font-extrabold text-slate-950">
                  {pet.petname}
                </p>
                <p className="mt-1 text-sm font-bold text-slate-500">
                  {getPetMeta(pet) || t("schedule.fieldPet")}
                </p>
              </div>

              <label className="block">
                <span className="text-sm font-extrabold text-slate-900">
                  {t("schedule.fieldDate")}
                </span>
                <div className="mt-1.5 flex items-center rounded-xl border border-slate-200 bg-white px-4 transition focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-100">
                  <input
                    ref={dateInputRef}
                    type="date"
                    value={selectedDate}
                    min={new Date().toISOString().slice(0, 10)}
                    onChange={(event) => setSelectedDate(event.target.value)}
                    className="h-11 flex-1 cursor-pointer bg-transparent text-sm font-bold text-slate-900 outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleOpenDatePicker}
                    className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-50 hover:text-slate-700"
                    aria-label={t("schedule.openCalendar")}
                  >
                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                      <line x1="16" y1="2" x2="16" y2="6" />
                      <line x1="8" y1="2" x2="8" y2="6" />
                      <line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  </button>
                </div>
              </label>

              <section>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-extrabold text-slate-900">
                    {t("schedule.availableTime")}
                  </h3>
                  <p className="text-xs font-bold text-slate-400">
                    {selectedDate}
                  </p>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {isLoadingSlots ? (
                    Array.from({ length: 8 }).map((_, index) => (
                      <div
                        key={index}
                        className="h-10 animate-pulse rounded-xl bg-slate-100"
                      />
                    ))
                  ) : availableSlots.length > 0 ? (
                    availableSlots.map((slot) => {
                      const isSelected =
                        selectedSlot?.start_time === slot.start_time;

                      return (
                        <button
                          key={`${slot.start_time}-${slot.end_time}`}
                          type="button"
                          onClick={() => setSelectedSlot(slot)}
                          className={[
                            "h-10 rounded-xl border text-sm font-extrabold transition",
                            isSelected
                              ? "border-blue-600 bg-blue-600 text-white"
                              : "border-blue-100 text-blue-600 hover:bg-blue-50",
                          ].join(" ")}
                        >
                          {slot.start_time}
                        </button>
                      );
                    })
                  ) : (
                    <p className="col-span-3 rounded-xl bg-slate-50 px-4 py-8 text-center text-sm font-bold text-slate-500 sm:col-span-4">
                      {t("schedule.noSlots")}
                    </p>
                  )}
                </div>
              </section>

              <label className="block">
                <span className="text-sm font-extrabold text-slate-900">
                  {t("schedule.fieldMemo")}
                </span>
                <textarea
                  value={memo}
                  onChange={(event) => setMemo(event.target.value)}
                  placeholder={t("schedule.memoPlaceholder")}
                  rows={3}
                  className="mt-1.5 w-full resize-none rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                />
              </label>

              {errorMessage ? (
                <div className="rounded-xl bg-rose-50 px-4 py-3 text-sm font-bold text-rose-600">
                  {errorMessage}
                </div>
              ) : null}
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-100 px-5 py-3.5 sm:px-6">
              <ActionButton
                type="button"
                onClick={onClose}
                disabled={isSubmitting}
                variant="secondary"
              >
                {t("common.close")}
              </ActionButton>
              <ActionButton
                type="submit"
                disabled={!selectedSlot || isSubmitting}
                className="min-w-[112px]"
              >
                {isSubmitting ? t("schedule.reserving") : t("schedule.reserve")}
              </ActionButton>
            </div>
          </form>
        )}
      </section>
    </div>
  );
};

export default CheckupReservationModal;
