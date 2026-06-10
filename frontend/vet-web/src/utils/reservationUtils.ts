import {
  addDays as addDateFnsDays,
  addMonths as addDateFnsMonths,
  eachDayOfInterval,
  format,
  isSaturday,
  isSameDay,
  isSunday,
  parse,
  startOfDay as startOfDateFnsDay,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import Holidays from "date-holidays";
import { toGenderLabel } from "./genderUtils";
import type {
  PatientDetailResponse,
  PatientListItemResponse,
} from "../api/patientApi";
import type {
  ApiReservation,
  PatientsById,
  ReservationItem,
  ReservationPatient,
  ReservationStatus,
  ReservationViewMode,
} from "../types/reservation";

export const reservationStatusMeta: Record<
  ReservationStatus,
  { label: string; badgeClass: string; softClass: string }
> = {
  emergency: {
    label: "응급",
    badgeClass: "border border-red-100 bg-red-50 text-red-500",
    softClass: "border border-red-100 bg-red-50 text-red-500",
  },
  semiEmergency: {
    label: "준응급",
    badgeClass: "border border-amber-100 bg-amber-50 text-amber-600",
    softClass: "border border-amber-100 bg-amber-50 text-amber-600",
  },
  normal: {
    label: "일반",
    badgeClass: "border border-green-100 bg-green-50 text-green-700",
    softClass: "border border-green-100 bg-green-50 text-green-700",
  },
};

export const DEFAULT_PET_IMAGE =
  "https://images.unsplash.com/photo-1583511655826-05700d52f4d9?auto=format&fit=crop&w=240&q=80";

export const dayLabels = ["일", "월", "화", "수", "목", "금", "토"];
export const weekDayLabels = ["월", "화", "수", "목", "금", "토", "일"];

export const statusOrder: ReservationStatus[] = [
  "emergency",
  "semiEmergency",
  "normal",
];

export const weeklyCardClass: Record<ReservationStatus, string> = {
  emergency: "border-red-100 bg-red-50 text-slate-800 before:bg-red-500",
  semiEmergency: "border-amber-100 bg-amber-50 text-slate-800 before:bg-amber-600",
  normal: "border-green-100 bg-green-50 text-slate-800 before:bg-green-500",
};

const koreanHolidayProvider = new Holidays("KR", {
  languages: "ko",
  types: ["public"],
});

const holidayNameAliases: Record<string, string> = {
  "3·1절": "삼일절",
  석가탄신일: "부처님오신날",
  기독탄신일: "성탄절",
};

const oneTimeKoreanHolidays: Record<string, string> = {
  "2026-06-03": "전국동시지방선거",
};

const fixedDisplayHolidays: Record<string, string> = {
  "05-01": "근로자의날",
};

const substitutionEligibleNames = new Set([
  "삼일절",
  "어린이날",
  "부처님오신날",
  "광복절",
  "개천절",
  "한글날",
  "성탄절",
]);

const koreanHolidayCache: Record<number, Record<string, string>> = {};

export function dotDate(value: string) {
  return value ? value.replace(/-/g, ".") : "";
}

export function formatGender(value?: string): ReservationPatient["gender"] {
  const label = toGenderLabel(value);
  if (label === "암컷") return "여자";
  if (label === "수컷") return "남자";
  return "미상";
}

export function mapApiReservations(items: ApiReservation[]): {
  reservations: ReservationItem[];
  patientsById: PatientsById;
} {
  const reservations: ReservationItem[] = [];
  const patientsById: PatientsById = {};

  for (const item of items) {
    reservations.push({
      id: item.schedule_id,
      patientId: item.petid,
      date: item.date,
      start: item.start,
      end: item.end,
      status: item.triage ?? "normal",
      visitReason: item.visit_reason,
      doctorName: item.doctor_name,
      memo: item.memo,
    });

    if (!patientsById[item.petid]) {
      patientsById[item.petid] = {
        id: item.petid,
        petName: item.pet_name,
        guardianName: item.owner_name,
        phone: item.phone,
        species: item.species || "",
        breed: item.breed,
        birthDate: dotDate(item.birth_date),
        age: item.age,
        weight: item.weight_kg ? `${item.weight_kg}kg` : "",
        gender: formatGender(item.gender),
        isNeutered: item.is_neutered,
        lastCheckupDate: dotDate(item.last_checkup_date),
        imageUrl: item.profile_image || DEFAULT_PET_IMAGE,
      };
    }
  }

  return { reservations, patientsById };
}

export function mapPatientListItemToReservationPatient(
  item: PatientListItemResponse
): ReservationPatient {
  return {
    id: item.petid,
    petName: item.petname,
    guardianName: item.owner_name,
    phone: item.phone,
    species: item.species || "",
    breed: item.breed,
    birthDate: "",
    age: item.age,
    weight: "",
    gender: "미상",
    isNeutered: false,
    lastCheckupDate: dotDate(item.last_visit_date),
    imageUrl: DEFAULT_PET_IMAGE,
  };
}

export function mapPatientDetailToReservationPatient(
  detail: PatientDetailResponse["result"],
  fallback: ReservationPatient
): ReservationPatient {
  const info = detail.patient_info;

  return {
    ...fallback,
    id: info.petid,
    petName: info.petname,
    guardianName: info.owner_name,
    phone: info.phone,
    species: info.species || "",
    breed: info.breed,
    birthDate: dotDate(info.birth_date),
    age: info.age,
    weight: info.weight_kg ? `${info.weight_kg}kg` : "",
    gender: formatGender(info.gender),
    isNeutered: info.is_neutered,
    imageUrl: info.profile_image || fallback.imageUrl || DEFAULT_PET_IMAGE,
  };
}

export function startOfDay(date: Date) {
  return startOfDateFnsDay(date);
}

export const TODAY = startOfDay(new Date());

export function addDays(date: Date, amount: number) {
  return addDateFnsDays(date, amount);
}

export function addMonths(date: Date, amount: number) {
  return startOfMonth(addDateFnsMonths(date, amount));
}

export function isSameDate(left: Date, right: Date) {
  return isSameDay(left, right);
}

export function getWeekDays(date: Date) {
  const monday = startOfWeek(date, { weekStartsOn: 1 });
  return Array.from({ length: 7 }, (_, index) => addDays(monday, index));
}

export function getMonthGrid(date: Date) {
  const monthStart = startOfMonth(date);
  const gridStart = startOfWeek(monthStart, { weekStartsOn: 0 });

  return eachDayOfInterval({
    start: gridStart,
    end: addDays(gridStart, 41),
  });
}

export function formatDate(date: Date) {
  return format(date, "yyyy.MM.dd");
}

export function formatDateWithWeekday(date: Date) {
  return `${formatDate(date)}(${dayLabels[date.getDay()]})`;
}

export function getDateKey(date: Date) {
  return format(date, "yyyy-MM-dd");
}

export function formatMonthTitle(date: Date) {
  return format(date, "yyyy년 MM월");
}

export function formatWeekRange(date: Date) {
  const days = getWeekDays(date);
  return `${formatDateWithWeekday(days[0])} ~ ${formatDateWithWeekday(days[6])}`;
}

export function getControlLabel(
  viewMode: ReservationViewMode,
  selectedDate: Date
) {
  if (viewMode === "week") {
    return formatWeekRange(selectedDate);
  }

  if (viewMode === "month") {
    return formatMonthTitle(selectedDate);
  }

  return formatDate(selectedDate);
}

export function getCompactControlLabel(
  viewMode: ReservationViewMode,
  selectedDate: Date
) {
  if (viewMode === "week") {
    const days = getWeekDays(selectedDate);
    return `${format(days[0], "MM.dd")}-${format(days[6], "MM.dd")}`;
  }

  if (viewMode === "month") {
    return format(selectedDate, "yyyy.MM");
  }

  return formatDate(selectedDate);
}

export function getHolidayName(date: Date) {
  return getKoreanHolidays(date.getFullYear())[getDateKey(date)];
}

function getKoreanHolidays(year: number) {
  koreanHolidayCache[year] ??= buildKoreanHolidays(year);
  return koreanHolidayCache[year];
}

function buildKoreanHolidays(year: number) {
  const holidays: Record<string, string> = {};
  const overlapSubstituteDates: Date[] = [];
  const baseHolidays = koreanHolidayProvider
    .getHolidays(year, "ko")
    .filter((holiday) => holiday.type === "public");

  for (const holiday of baseHolidays) {
    const dateKey = holiday.date.slice(0, 10);
    const name = normalizeHolidayName(holiday.name);

    if (name === "설날") {
      addHolidayRange(
        holidays,
        addDays(parseDateKey(dateKey), -1),
        3,
        "설날",
        overlapSubstituteDates
      );
      continue;
    }

    if (name === "추석") {
      addHolidayRange(
        holidays,
        parseDateKey(dateKey),
        3,
        "추석",
        overlapSubstituteDates
      );
      continue;
    }

    setKoreanHoliday(holidays, dateKey, name, overlapSubstituteDates);
  }

  for (const [monthDay, name] of Object.entries(fixedDisplayHolidays)) {
    setKoreanHoliday(holidays, `${year}-${monthDay}`, name, overlapSubstituteDates);
  }

  for (const [dateKey, name] of Object.entries(oneTimeKoreanHolidays)) {
    if (dateKey.startsWith(`${year}-`)) {
      setKoreanHoliday(holidays, dateKey, name, overlapSubstituteDates);
    }
  }

  addSubstituteHolidays(holidays, overlapSubstituteDates);

  return holidays;
}

function normalizeHolidayName(name: string) {
  return holidayNameAliases[name] ?? name;
}

function addHolidayRange(
  holidays: Record<string, string>,
  startDate: Date,
  length: number,
  name: string,
  overlapSubstituteDates: Date[]
) {
  for (let index = 0; index < length; index += 1) {
    const date = addDays(startDate, index);
    setKoreanHoliday(holidays, getDateKey(date), name, overlapSubstituteDates);
  }
}

function setKoreanHoliday(
  holidays: Record<string, string>,
  dateKey: string,
  name: string,
  overlapSubstituteDates: Date[]
) {
  if (holidays[dateKey] && holidays[dateKey] !== name) {
    overlapSubstituteDates.push(parseDateKey(dateKey));
    holidays[dateKey] = mergeHolidayNames(holidays[dateKey], name);
    return;
  }

  holidays[dateKey] = name;
}

function addSubstituteHolidays(
  holidays: Record<string, string>,
  overlapSubstituteDates: Date[]
) {
  const entries = Object.entries(holidays);
  const seollalKeys = entries
    .filter(([, name]) => hasHolidayName(name, "설날"))
    .map(([dateKey]) => dateKey);
  const chuseokKeys = entries
    .filter(([, name]) => hasHolidayName(name, "추석"))
    .map(([dateKey]) => dateKey);

  for (const [dateKey, name] of entries) {
    const date = parseDateKey(dateKey);

    if (isSubstitutionEligibleName(name) && isWeekend(date)) {
      addNextSubstituteHoliday(holidays, date);
    }
  }

  if (seollalKeys.some((dateKey) => isSunday(parseDateKey(dateKey)))) {
    addNextSubstituteHoliday(
      holidays,
      parseDateKey(seollalKeys[seollalKeys.length - 1])
    );
  }

  if (chuseokKeys.some((dateKey) => isSunday(parseDateKey(dateKey)))) {
    addNextSubstituteHoliday(
      holidays,
      parseDateKey(chuseokKeys[chuseokKeys.length - 1])
    );
  }

  for (const date of overlapSubstituteDates) {
    addNextSubstituteHoliday(holidays, date);
  }
}

function addNextSubstituteHoliday(holidays: Record<string, string>, fromDate: Date) {
  let candidate = addDays(fromDate, 1);

  while (isWeekend(candidate) || holidays[getDateKey(candidate)]) {
    candidate = addDays(candidate, 1);
  }

  holidays[getDateKey(candidate)] = "대체공휴일";
}

function mergeHolidayNames(currentName: string, nextName: string) {
  const names = currentName.split("·");

  if (!names.includes(nextName)) {
    names.push(nextName);
  }

  return names.join("·");
}

function hasHolidayName(currentName: string, targetName: string) {
  return currentName.split("·").includes(targetName);
}

function isSubstitutionEligibleName(name: string) {
  return name
    .split("·")
    .some((holidayName) => substitutionEligibleNames.has(holidayName));
}

function isWeekend(date: Date) {
  return isSaturday(date) || isSunday(date);
}

function parseDateKey(dateKey: string) {
  return parse(dateKey, "yyyy-MM-dd", new Date());
}
