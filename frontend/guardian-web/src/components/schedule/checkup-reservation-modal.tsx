import React, { useRef } from "react";

import type { Pet } from "../../api/pets-api";
import { type HospitalDoctor } from "../../api/hospital-mock";
import { getHospitalDetail } from "../../api/hospital-api";
import { useHospitalStore } from "../../stores/hospital-store";
import ActionButton from "../common/action-button";
import { useCheckupReservation } from "../../hooks/use-checkup-reservation";
import { useTranslation } from "../../i18n/language-context";
import { logger } from "@shared/utils/logger";

interface CheckupReservationModalProps {
  pet: Pet;
  pets?: Pet[];
  onChangePet?: (pet: Pet) => void;
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
  pets,
  onChangePet,
  onClose,
}: CheckupReservationModalProps) => {
  const { t } = useTranslation();
  const [categoryCode, setCategoryCode] = React.useState<1 | 2 | null>(null);
  const categoryLabel = categoryCode === 2 ? "일반진료" : categoryCode === 1 ? "정기검진" : null;

  // 병원 → 원장 선택. 병원 목록·현재 병원은 전역 store, 원장은 병원 상세에서.
  const allHospitals = useHospitalStore((state) => state.myHospitals);
  // 폐업 병원은 신규 예약 대상에서 제외.
  const hospitals = React.useMemo(
    () => allHospitals.filter((h) => h.is_active !== false),
    [allHospitals],
  );
  const currentHospitalId = useHospitalStore((state) => state.currentHospitalId);
  const setCurrentHospital = useHospitalStore((state) => state.setCurrent);
  const [selectedHospitalId, setSelectedHospitalId] =
    React.useState<number | null>(currentHospitalId);
  const [doctors, setDoctors] = React.useState<HospitalDoctor[]>([]);
  const [selectedDoctorId, setSelectedDoctorId] = React.useState<number | null>(null);

  // 병원 목록 로드 후 선택값 보정(없거나 목록에 없거나 폐업이면 첫 영업 병원)
  React.useEffect(() => {
    if (hospitals.length === 0) return;
    setSelectedHospitalId((prev) =>
      prev != null && hospitals.some((h) => h.hospitalid === prev)
        ? prev
        : hospitals[0].hospitalid,
    );
  }, [hospitals]);

  // 선택 병원의 원장 목록 (실패 시 mock 폴백)
  React.useEffect(() => {
    if (selectedHospitalId == null) {
      setDoctors([]);
      return;
    }
    let mounted = true;
    getHospitalDetail(selectedHospitalId)
      .then((d) => {
        if (mounted) setDoctors(d.doctors ?? []);
      })
      .catch(() => {
        if (mounted) setDoctors([]);
      });
    return () => {
      mounted = false;
    };
  }, [selectedHospitalId]);
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
    slotsMessage,
    completedReservation,
    setSelectedDate,
    setSelectedSlot,
    setMemo,
    reserveCheckup,
  } = useCheckupReservation({
    petId: pet.pet_id,
    categoryCode: categoryCode ?? 1,
    hospitalId: selectedHospitalId ?? undefined,
    doctorId: selectedDoctorId ?? undefined,
  });

  const handleSelectHospital = (id: number) => {
    setSelectedHospitalId(id);
    setCurrentHospital(id); // 앱 전역 현재 병원도 함께 전환
    setSelectedDoctorId(null);
    setSelectedSlot(null);
  };

  const handleSelectDoctor = (id: number) => {
    setSelectedDoctorId(id);
    setSelectedSlot(null);
  };
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
      logger.warn("showPicker failed, falling back to focus:", error);
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
                {t("schedule.completeDesc", {
                  date: completedReservation.date,
                  time: `${completedReservation.time} - ${completedReservation.end_time}`,
                })}
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
                {t("schedule.completeConfirm")}
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
              <div className="flex items-center justify-center gap-3 py-1">
                <div className="h-10 w-10 shrink-0 overflow-hidden rounded-full bg-slate-100 shadow-sm">
                  <img
                    src={pet.profile_image || `/assets/profile${(Math.abs(pet.pet_id) % 6) + 1}.png`}
                    alt={pet.petname}
                    className="h-full w-full object-cover"
                  />
                </div>
                {pets && pets.length > 1 ? (
                  <div className="relative">
                    <select
                      value={pet.pet_id}
                      onChange={(e) => {
                        const selected = pets.find((p) => p.pet_id === Number(e.target.value));
                        if (selected && onChangePet) onChangePet(selected);
                      }}
                      className="w-full appearance-none bg-transparent py-1 pr-6 text-lg font-extrabold text-slate-900 outline-none cursor-pointer"
                    >
                      {pets.map((p) => (
                        <option key={p.pet_id} value={p.pet_id}>
                          {p.petname}
                        </option>
                      ))}
                    </select>
                    <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center text-slate-400">
                      <svg className="h-5 w-5 fill-current" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </div>
                ) : (
                  <p className="text-lg font-extrabold text-slate-900">
                    {pet.petname}
                  </p>
                )}
              </div>

              <div className="space-y-1.5">
                <span className="text-sm font-extrabold text-slate-900">
                  진료 타입 <span className="text-rose-500">*</span>
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setCategoryCode(2)}
                    className={[
                      "inline-flex h-10 flex-1 items-center justify-center rounded-xl text-sm font-bold transition",
                      categoryCode === 2
                        ? "bg-blue-600 text-white"
                        : "border border-slate-200 text-slate-600 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    일반진료
                  </button>
                  <button
                    type="button"
                    onClick={() => setCategoryCode(1)}
                    className={[
                      "inline-flex h-10 flex-1 items-center justify-center rounded-xl text-sm font-bold transition",
                      categoryCode === 1
                        ? "bg-blue-600 text-white"
                        : "border border-slate-200 text-slate-600 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    정기검진
                  </button>
                </div>
              </div>

              {/* 병원 선택 */}
              <div className="space-y-1.5">
                <span className="text-sm font-extrabold text-slate-900">
                  {t("schedule.fieldHospital")} <span className="text-rose-500">*</span>
                </span>
                <div className="relative">
                  <select
                    value={selectedHospitalId ?? ""}
                    onChange={(event) => handleSelectHospital(Number(event.target.value))}
                    className="h-11 w-full appearance-none rounded-xl border border-slate-200 bg-white px-4 pr-9 text-sm font-bold text-slate-900 outline-none transition focus:border-blue-400 focus:ring-4 focus:ring-blue-100"
                  >
                    {hospitals.map((hospital) => (
                      <option key={hospital.hospitalid} value={hospital.hospitalid}>
                        {hospital.name}
                      </option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-slate-400">
                    <svg className="h-5 w-5 fill-current" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </div>
                </div>
              </div>

              {/* 원장 선택 */}
              <div className="space-y-1.5">
                <span className="text-sm font-extrabold text-slate-900">
                  {t("schedule.fieldDoctor")} <span className="text-rose-500">*</span>
                </span>
                {doctors.length > 0 ? (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {doctors.map((doctor) => {
                      const isSelected = selectedDoctorId === doctor.doctorid;
                      return (
                        <button
                          key={doctor.doctorid}
                          type="button"
                          onClick={() => handleSelectDoctor(doctor.doctorid)}
                          className={[
                            "flex flex-col items-center gap-0.5 rounded-xl border px-2 py-2.5 text-center transition",
                            isSelected
                              ? "border-blue-600 bg-blue-50"
                              : "border-slate-200 hover:bg-slate-50",
                          ].join(" ")}
                        >
                          <span className="text-sm font-bold text-slate-900">{doctor.name}</span>
                          {doctor.specialty ? (
                            <span className="text-xs font-semibold text-slate-500">
                              {doctor.specialty}
                            </span>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm font-bold text-slate-500">
                    {t("schedule.noDoctors")}
                  </p>
                )}
              </div>

              <label className="block">
                <span className="text-sm font-extrabold text-slate-900">
                  {t("schedule.fieldDate")} <span className="text-rose-500">*</span>
                </span>
                <div className="mt-1.5 flex items-center rounded-xl border border-slate-200 bg-white px-4 transition focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-100">
                  <input
                    type="text"
                    placeholder="날짜를 입력해주세요"
                    maxLength={10}
                    value={selectedDate.replace(/-/g, ".")}
                    onChange={(event) => {
                      const input = event.target.value.replace(/[^0-9]/g, "");
                      let formatted = input;
                      if (input.length > 8) {
                        formatted = input.slice(0, 8);
                      }
                      if (formatted.length > 6) {
                        formatted = `${formatted.slice(0, 4)}-${formatted.slice(4, 6)}-${formatted.slice(6)}`;
                      } else if (formatted.length > 4) {
                        formatted = `${formatted.slice(0, 4)}-${formatted.slice(4)}`;
                      }
                      setSelectedDate(formatted);
                    }}
                    className="h-11 flex-1 bg-transparent text-sm font-bold text-slate-900 outline-none placeholder:text-slate-400 placeholder:font-semibold"
                  />
                  <input
                    ref={dateInputRef}
                    type="date"
                    value={selectedDate.length === 10 ? selectedDate : ""}
                    min={new Date().toISOString().slice(0, 10)}
                    onChange={(event) => setSelectedDate(event.target.value)}
                    className="sr-only"
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
                      {slotsMessage || t("schedule.noSlots")}
                    </p>
                  )}
                </div>
              </section>

              <label className="block">
                <span className="text-sm font-extrabold text-slate-900">
                  {t("schedule.fieldMemo")} <span className="font-semibold text-slate-400">(선택 사항)</span>
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
                disabled={
                  !selectedSlot ||
                  isSubmitting ||
                  categoryCode === null ||
                  selectedDoctorId === null
                }
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
