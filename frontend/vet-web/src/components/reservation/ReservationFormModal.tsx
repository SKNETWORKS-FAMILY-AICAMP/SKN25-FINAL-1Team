import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";
import type { DoctorInfo } from "../../api/emrApi";
import type {
  ReservationFormState,
  ReservationItem,
  ReservationPatient,
} from "../../types/reservation";
import {
  TODAY,
  addMonths,
  dayLabels,
  formatDateWithWeekday,
  formatMonthTitle,
  getDateKey,
  getHolidayName,
  getMonthGrid,
  isSameDate,
} from "../../utils/reservationUtils";
import {
  type DayHours,
  useClosedDates,
  useOperatingHoursForDate,
} from "../../contexts/OperatingHoursContext";
import {
  formatMinutesAsTime,
  parseTimeToMinutes,
} from "../../utils/scheduleTimelineUtils";

function generateTimeOptions(hours: DayHours): string[] {
  const startMin = parseTimeToMinutes(hours.startTime);
  const endMin = parseTimeToMinutes(hours.endTime);
  const lunchStartMin = parseTimeToMinutes(hours.lunchStart);
  const lunchEndMin = parseTimeToMinutes(hours.lunchEnd);

  const options: string[] = [];
  for (let min = startMin; min <= endMin - 30; min += 30) {
    if (min >= lunchStartMin && min < lunchEndMin) continue;
    options.push(formatMinutesAsTime(min));
  }
  return options;
}

interface ReservationFormModalProps {
  mode: "add" | "edit";
  selectedDate: Date;
  reservation?: ReservationItem;
  reservations: ReservationItem[];
  patient?: ReservationPatient;
  patientOptions: ReservationPatient[];
  doctors: DoctorInfo[];
  onClose: () => void;
  onResolvePatient?: (patient: ReservationPatient) => Promise<ReservationPatient>;
  onSave: (patient: ReservationPatient, form: ReservationFormState) => void;
}

export function ReservationFormModal({
  mode,
  selectedDate,
  reservation,
  reservations,
  patient,
  patientOptions,
  doctors,
  onClose,
  onResolvePatient,
  onSave,
}: ReservationFormModalProps) {
  useEscapeToClose(onClose);

  const [searchText, setSearchText] = useState("");
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [activePatientIndex, setActivePatientIndex] = useState(0);
  const patientSearchId = useId();
  const patientListboxId = `${patientSearchId}-patient-results`;
  const patientResolveRequestIdRef = useRef(0);
  const [selectedPatient, setSelectedPatient] = useState<ReservationPatient | null>(
    mode === "edit" ? patient ?? null : null
  );
  const [reservationDate, setReservationDate] = useState(selectedDate);
  const dayHours = useOperatingHoursForDate(reservationDate);
  const closedDates = useClosedDates();
  const [form, setForm] = useState<ReservationFormState>({
    date: formatDateWithWeekday(selectedDate),
    dateKey: getDateKey(selectedDate),
    time: reservation?.start ?? "17:00",
    doctorName: reservation?.doctorName ?? doctors[0]?.doctor_name ?? "",
    memo: reservation?.memo ?? "",
    categoryCode: null,
  });

  const isClosedDay = dayHours === null;
  const isSpecificClosed = isClosedDay && closedDates.has(form.dateKey);

  const timeOptions = useMemo(
    () => (dayHours ? generateTimeOptions(dayHours) : []),
    [dayHours]
  );

  const filteredPatients = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) {
      return [];
    }

    return patientOptions.filter((item) =>
      `${item.petName} ${item.guardianName} ${item.phone} ${item.breed}`
        .toLowerCase()
        .includes(keyword)
    );
  }, [searchText, patientOptions]);

  useEffect(() => {
    setActivePatientIndex(0);
  }, [searchText]);

  useEffect(() => {
    if (activePatientIndex > filteredPatients.length - 1) {
      setActivePatientIndex(Math.max(filteredPatients.length - 1, 0));
    }
  }, [activePatientIndex, filteredPatients.length]);

  // 선택한 날짜 + 선택한 의사 기준으로 이미 예약된 시작 시간(수정 중인 본인 예약은 제외)
  const bookedTimes = useMemo(() => {
    const taken = new Set<string>();
    for (const item of reservations) {
      if (
        item.date === form.dateKey &&
        item.id !== reservation?.id &&
        item.doctorName === form.doctorName
      ) {
        taken.add(item.start);
      }
    }
    return taken;
  }, [reservations, form.dateKey, reservation?.id, form.doctorName]);

  // 예약된 시간 + 오늘 기준 지난 시간은 선택지에서 숨긴다
  const availableTimeOptions = useMemo(() => {
    const isToday = form.dateKey === getDateKey(TODAY);
    const now = new Date();
    const currentHHMM = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

    return timeOptions.filter((time) => {
      if (bookedTimes.has(time)) return false;
      if (isToday && time <= currentHHMM) return false;
      return true;
    });
  }, [timeOptions, bookedTimes, form.dateKey]);

  // 날짜를 바꿔 현재 선택한 시간이 선택 불가(예약됨 or 오늘 지난 시간)해지면 가능한 첫 시간으로 보정
  useEffect(() => {
    if (form.time && availableTimeOptions.length > 0 && !availableTimeOptions.includes(form.time)) {
      setForm((current) => ({
        ...current,
        time: availableTimeOptions[0] ?? "",
      }));
    }
  }, [availableTimeOptions, form.time]);

  const handleSelectPatient = async (item: ReservationPatient) => {
    const requestId = patientResolveRequestIdRef.current + 1;
    patientResolveRequestIdRef.current = requestId;

    setSelectedPatient(item);
    setSearchText(`${item.petName} (${item.guardianName})`);
    setIsSearchFocused(false);

    if (!onResolvePatient) {
      return;
    }

    const resolvedPatient = await onResolvePatient(item);

    if (patientResolveRequestIdRef.current === requestId) {
      setSelectedPatient(resolvedPatient);
    }
  };

  const hasPatientSearchKeyword = searchText.trim().length > 0;
  const shouldShowSearchResults = isSearchFocused && hasPatientSearchKeyword;
  const canSaveReservation = selectedPatient !== null && form.categoryCode !== null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 px-4 py-3">
      <div className="flex max-h-[94vh] w-full max-w-[560px] flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="text-base font-extrabold text-slate-900">
            예약 {mode === "add" ? "추가" : "수정"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-50"
            aria-label="닫기"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {mode === "add" && (
            <div className="relative">
              <label className="mb-1.5 block text-xs font-extrabold text-slate-800">
                환자 검색
              </label>
              <div className="flex h-9 items-center rounded-lg border border-slate-200 px-3 focus-within:border-blue-600">
                <input
                  value={searchText}
                  onFocus={() => setIsSearchFocused(true)}
                  onBlur={() => window.setTimeout(() => setIsSearchFocused(false), 120)}
                  onChange={(event) => setSearchText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowDown") {
                      event.preventDefault();
                      if (hasPatientSearchKeyword && filteredPatients.length > 0) {
                        setIsSearchFocused(true);
                        setActivePatientIndex((index) =>
                          Math.min(index + 1, filteredPatients.length - 1)
                        );
                      }
                    }

                    if (event.key === "ArrowUp") {
                      event.preventDefault();
                      if (hasPatientSearchKeyword && filteredPatients.length > 0) {
                        setIsSearchFocused(true);
                        setActivePatientIndex((index) => Math.max(index - 1, 0));
                      }
                    }

                    if (
                      event.key === "Enter" &&
                      shouldShowSearchResults &&
                      filteredPatients[activePatientIndex]
                    ) {
                      event.preventDefault();
                      void handleSelectPatient(filteredPatients[activePatientIndex]);
                    }

                    if (event.key === "Escape") {
                      setIsSearchFocused(false);
                    }
                  }}
                  placeholder="강아지이름 / 전화번호 뒷자리 검색"
                  role="combobox"
                  aria-autocomplete="list"
                  aria-expanded={shouldShowSearchResults}
                  aria-controls={patientListboxId}
                  aria-activedescendant={
                    shouldShowSearchResults && filteredPatients[activePatientIndex]
                      ? `${patientListboxId}-${activePatientIndex}`
                      : undefined
                  }
                  className="min-w-0 flex-1 bg-transparent text-xs font-bold text-slate-800 outline-none placeholder:text-slate-400"
                />
                <ChevronDown className="h-4 w-4 text-slate-600" />
              </div>
              {shouldShowSearchResults && (
                <div
                  id={patientListboxId}
                  role="listbox"
                  className="absolute left-0 right-0 top-[62px] z-10 max-h-64 overflow-y-auto rounded-lg border border-slate-100 bg-white shadow-lg"
                >
                  {filteredPatients.length > 0 ? (
                    filteredPatients.map((item, index) => (
                      <button
                        key={item.id}
                        type="button"
                        id={`${patientListboxId}-${index}`}
                        role="option"
                        aria-selected={index === activePatientIndex}
                        onMouseEnter={() => setActivePatientIndex(index)}
                        onClick={() => void handleSelectPatient(item)}
                        className={[
                          "flex w-full items-center justify-between border-b border-slate-50 px-4 py-2.5 text-left last:border-b-0",
                          index === activePatientIndex ? "bg-blue-50" : "hover:bg-slate-50",
                        ].join(" ")}
                      >
                        <span>
                          <span className="block text-sm font-extrabold text-slate-800">
                            {item.petName} ({item.guardianName})
                          </span>
                          <span className="mt-1 block text-xs font-bold text-slate-400">
                            {item.phone}
                          </span>
                        </span>
                        <span className="text-xs font-extrabold text-slate-400">
                          {item.species}
                        </span>
                      </button>
                    ))
                  ) : (
                    <div className="px-4 py-3 text-sm font-bold text-slate-400">
                      검색 결과가 없습니다.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <section>
            <h3 className="mb-2 text-sm font-extrabold text-slate-800">
              정보 확인
            </h3>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <ReadonlyField label="강아지 이름" value={selectedPatient?.petName ?? ""} />
              <ReadonlyField label="생년월일" value={selectedPatient?.birthDate ?? ""} />
              <ReadonlyField label="종" value={selectedPatient?.species ?? ""} />
              <ReadonlyField label="몸무게" value={selectedPatient?.weight ?? ""} />
              <ReadonlyField label="품종" value={selectedPatient?.breed ?? ""} />
              <ReadonlyField
                label="마지막 정기검진날"
                value={selectedPatient?.lastCheckupDate ?? ""}
              />
              <ReadonlyField label="성별" value={selectedPatient?.gender ?? ""} />
              <ReadonlyField
                label="중성화 여부"
                value={
                  selectedPatient
                    ? selectedPatient.isNeutered
                      ? "중성화 O"
                      : "중성화 X"
                    : ""
                }
              />
            </div>
          </section>

          <section className="border-t border-slate-100 pt-3">
            <h3 className="mb-2 text-sm font-extrabold text-slate-800">
              예약 정보
            </h3>
            <div className="mb-3 flex gap-2">
              {([2, 1] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => setForm((cur) => ({ ...cur, categoryCode: code }))}
                  className={[
                    "flex-1 h-9 rounded-lg text-xs font-extrabold transition",
                    form.categoryCode === code
                      ? "bg-blue-600 text-white"
                      : "border border-slate-200 text-slate-800 hover:bg-blue-50",
                  ].join(" ")}
                >
                  {code === 2 ? "일반진료" : "정기검진"}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <DatePickerField
                label="예약 날짜"
                selectedDate={reservationDate}
                onSelectDate={(date) => {
                  setReservationDate(date);
                  setForm((current) => ({
                    ...current,
                    date: formatDateWithWeekday(date),
                    dateKey: getDateKey(date),
                  }));
                }}
              />
              <SelectField
                label="예약 시간"
                value={form.time}
                options={availableTimeOptions}
                onChange={(value) => setForm((current) => ({ ...current, time: value }))}
              />
              <SelectField
                label="담당 수의사"
                value={form.doctorName}
                options={doctors.map((d) => d.doctor_name)}
                onChange={(value) =>
                  setForm((current) => ({ ...current, doctorName: value }))
                }
              />
            </div>
            {isClosedDay && (
              <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700">
                {isSpecificClosed
                  ? "특정일 휴진으로 지정된 날짜입니다. 예약을 추가할 수 없습니다."
                  : "병원 운영 요일이 아닙니다. 예약을 추가할 수 없습니다."}
              </p>
            )}
            <label className="mt-3 block text-xs font-extrabold text-slate-800">
              <span className="mb-1 block">메모</span>
              <span className="relative">
                <textarea
                  value={form.memo}
                  maxLength={200}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, memo: event.target.value }))
                  }
                  className="h-20 w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:border-blue-600"
                />
                <span className="absolute bottom-3 right-3 text-xs font-extrabold text-slate-400">
                  {form.memo.length} / 200
                </span>
              </span>
            </label>
          </section>
        </div>

        <div className="grid shrink-0 grid-cols-2 gap-4 px-5 pb-5 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-blue-100 text-sm font-extrabold text-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            disabled={!canSaveReservation}
            onClick={() => {
              if (selectedPatient) {
                onSave(selectedPatient, form);
              }
            }}
            className="h-10 rounded-lg bg-blue-600 text-sm font-extrabold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            예약 저장
          </button>
        </div>
      </div>
    </div>
  );
}

function ReadonlyField({ label, value }: { label: string; value: string }) {
  return (
    <label className="block min-w-0 text-xs font-extrabold text-slate-800">
      <span className="mb-1 block">{label}</span>
      <input
        readOnly
        value={value}
        className="h-8 w-full min-w-0 rounded-lg border border-slate-100 bg-slate-50 px-3 text-xs font-bold text-slate-600 outline-none"
      />
    </label>
  );
}

function DatePickerField({
  label,
  selectedDate,
  onSelectDate,
}: {
  label: string;
  selectedDate: Date;
  onSelectDate: (date: Date) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ left: 0, top: 0 });
  const calendarButtonRef = useRef<HTMLButtonElement | null>(null);
  const [visibleMonth, setVisibleMonth] = useState(
    new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1)
  );
  const days = getMonthGrid(visibleMonth);

  const toggleCalendar = () => {
    const rect = calendarButtonRef.current?.getBoundingClientRect();

    if (rect) {
      const popoverWidth = 244;
      const left = Math.min(
        Math.max(12, rect.right - popoverWidth),
        window.innerWidth - popoverWidth - 12
      );
      setPopoverPosition({
        left,
        top: rect.bottom + 8,
      });
    }

    setIsOpen((open) => !open);
  };

  return (
    <label className="block min-w-0 text-xs font-extrabold text-slate-800">
      <span className="mb-1 block">{label}</span>
      <span className="flex h-8 min-w-0 items-center rounded-lg border border-slate-200 px-3">
        <input
          readOnly
          value={formatDateWithWeekday(selectedDate)}
          className="min-w-0 flex-1 cursor-default bg-transparent text-xs font-bold text-slate-800 outline-none"
        />
        <button
          ref={calendarButtonRef}
          type="button"
          onClick={toggleCalendar}
          className="flex h-6 w-6 items-center justify-center rounded-md text-slate-600 hover:bg-blue-50 hover:text-blue-600"
          aria-label="예약 날짜 선택"
        >
          <CalendarDays className="h-4 w-4" />
        </button>
      </span>

      {isOpen && (
        <div
          className="fixed z-[70] w-[244px] rounded-lg border border-slate-200 bg-white p-3 shadow-xl"
          style={{
            left: popoverPosition.left,
            top: popoverPosition.top,
          }}
        >
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setVisibleMonth((date) => addMonths(date, -1))}
              className="flex h-7 w-7 items-center justify-center rounded-md text-slate-600 hover:bg-slate-50"
              aria-label="이전 달"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-extrabold text-slate-800">
              {formatMonthTitle(visibleMonth)}
            </span>
            <button
              type="button"
              onClick={() => setVisibleMonth((date) => addMonths(date, 1))}
              className="flex h-7 w-7 items-center justify-center rounded-md text-slate-600 hover:bg-slate-50"
              aria-label="다음 달"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-extrabold text-slate-400">
            {dayLabels.map((day) => (
              <span key={day}>{day}</span>
            ))}
            {days.map((day) => {
              const isCurrentMonth = day.getMonth() === visibleMonth.getMonth();
              const isSelected = isSameDate(day, selectedDate);
              const isToday = isSameDate(day, TODAY);
              const isHoliday = Boolean(getHolidayName(day));
              const isSunday = day.getDay() === 0;
              const isSaturday = day.getDay() === 6;
              const isPast = day < TODAY && !isToday;

              return (
                <button
                  key={day.toISOString()}
                  type="button"
                  disabled={isPast}
                  onClick={() => {
                    onSelectDate(day);
                    setVisibleMonth(new Date(day.getFullYear(), day.getMonth(), 1));
                    setIsOpen(false);
                  }}
                  title={getHolidayName(day)}
                  className={[
                    "flex h-7 items-center justify-center rounded-md text-xs font-extrabold transition",
                    isPast
                      ? "cursor-not-allowed text-slate-300 line-through"
                      : isSelected
                        ? "bg-blue-600 text-white"
                        : isToday
                          ? "border border-blue-600 text-blue-600"
                          : !isCurrentMonth
                            ? "text-slate-300"
                            : isHoliday || isSunday
                              ? "text-red-500 hover:bg-red-50"
                              : isSaturday
                                ? "text-blue-600 hover:bg-blue-50"
                                : "text-slate-800 hover:bg-slate-50",
                  ].join(" ")}
                >
                  {day.getDate()}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block min-w-0 text-xs font-extrabold text-slate-800">
      <span className="mb-1 block">{label}</span>
      <span className="relative block min-w-0">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-8 w-full appearance-none rounded-lg border border-slate-200 bg-white px-3 pr-8 text-xs font-bold text-slate-800 outline-none focus:border-blue-600"
        >
          <option value="">선택</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-2 h-4 w-4 text-slate-600" />
      </span>
    </label>
  );
}
