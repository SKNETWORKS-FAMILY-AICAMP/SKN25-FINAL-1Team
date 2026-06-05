type GenderKey = "female" | "male" | "unknown";

const GENDER_META: Record<GenderKey, { symbol: "♀" | "♂" | "-"; label: string }> = {
  female:  { symbol: "♀", label: "암컷" },
  male:    { symbol: "♂", label: "수컷" },
  unknown: { symbol: "-", label: "성별 모름" },
};

const FEMALE_KEYS = new Set(["female", "f", "여자", "여아", "암컷"]);
const MALE_KEYS   = new Set(["male",   "m", "남자", "남아", "수컷"]);

export function normalizeGender(gender?: string): GenderKey {
  const g = (gender ?? "").toLowerCase().trim();
  if (FEMALE_KEYS.has(g)) return "female";
  if (MALE_KEYS.has(g))   return "male";
  return "unknown";
}

export function toGenderLabel(gender?: string): string {
  return GENDER_META[normalizeGender(gender)].label;
}

export function toGenderSymbol(gender?: string): "♀" | "♂" | "-" {
  return GENDER_META[normalizeGender(gender)].symbol;
}
