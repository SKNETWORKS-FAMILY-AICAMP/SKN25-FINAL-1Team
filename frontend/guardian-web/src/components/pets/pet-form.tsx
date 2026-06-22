import { useRef, type ChangeEvent, type RefObject } from "react";

import {
  genderOptions,
  maxNotesLength,
  neuteredOptions,
  type PetFormErrors,
  type PetFormState,
  speciesOptions,
} from "../../hooks/use-pet-form";
import { useTranslation } from "../../i18n/language-context";

const inputClass =
  "h-12 w-full rounded-xl bg-[#F8FAFC] px-4 text-sm font-semibold text-[#1F2937] outline-none transition-all duration-300 placeholder:text-[#6B7280] border border-[#E5E7EB] focus:border-[#2F6F67] focus:bg-white focus:ring-4 focus:ring-[#2F6F67]/10 hover:border-[#6B7280]/30";
const selectClass = inputClass;
const errorInputClass = "!border-red-400 focus:!border-red-500 focus:!ring-red-100 bg-red-50/30";
const labelClass = "text-sm font-bold text-[#1F2937] ml-1 mb-2 block";

const FieldError = ({ message }: { message?: string }) =>
  message ? <p className="mt-1 text-[10px] font-semibold text-red-500">{message}</p> : null;

const RequiredMark = () => <span className="ml-0.5 text-red-500">*</span>;

// PawIcon removed as requested

const choiceTone = {
  blue: "border-blue-300 bg-blue-50 text-blue-700",
  pink: "border-pink-300 bg-pink-50 text-pink-700",
  green: "border-emerald-300 bg-emerald-50 text-emerald-700",
  orange: "border-orange-300 bg-orange-50 text-orange-700",
  teal: "border-teal-300 bg-teal-50 text-teal-700",
  slate: "border-slate-300 bg-slate-50 text-slate-700",
};

const getChoiceClass = (
  isSelected: boolean,
  tone: keyof typeof choiceTone = "slate",
) =>
  [
    "flex flex-row h-14 items-center justify-center gap-2 rounded-xl border-2 transition-all duration-300 group cursor-pointer w-full text-center outline-none relative",
    isSelected
      ? "border-[#2F6F67] bg-[#2F6F67]/5 text-[#2F6F67]"
      : "border-[#E5E7EB] bg-white text-[#6B7280] hover:border-[#2F6F67]/30 hover:bg-[#F8FAFC]",
  ].join(" ");

const localeForLang = (lang: string) =>
  ({ ko: "ko-KR", en: "en-US", ja: "ja-JP", zh: "zh-CN" })[lang] || "ko-KR";

const formatDatePreview = (value: string, lang: string) => {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(localeForLang(lang), {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
};

interface LocalizedDateInputProps {
  id: string;
  label: string;
  value: string;
  disabled: boolean;
  lang: string;
  onChange: (value: string) => void;
}

const LocalizedDateInput = ({
  id,
  label,
  value,
  disabled,
  lang,
  onChange,
}: LocalizedDateInputProps) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const displayValue = value ? formatDatePreview(value, lang) : label;

  // 데스크톱에서 투명 input을 클릭하면 달력을 바로 띄운다. 모바일은 투명 input을
  // 직접 탭하면 OS 네이티브 날짜 휠이 열리므로, showPicker가 실패해도 무시한다.
  const openPicker = () => {
    if (disabled) return;
    const input = inputRef.current;
    if (!input) return;
    if (typeof input.showPicker === "function") {
      try {
        input.showPicker();
      } catch {
        input.focus();
      }
    } else {
      input.focus();
    }
  };

  return (
    <div className="relative mt-2">
      {/* 보이는 부분(스타일). 실제 입력/탭은 위에 겹친 투명 input이 직접 받는다. */}
      <div
        aria-hidden="true"
        className={[
          "flex h-12 w-full items-center justify-between rounded-xl border border-[#E5E7EB] bg-[#F8FAFC] px-4 text-left text-sm font-semibold transition-all duration-300",
          disabled ? "bg-slate-100 text-slate-400" : "text-[#1F2937]",
        ].join(" ")}
      >
        <span className={value ? "text-slate-900" : "text-slate-400"}>
          {displayValue}
        </span>
        <span className="text-slate-500" aria-hidden="true">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="4" width="18" height="18" rx="2" />
            <path d="M8 2v4M16 2v4M3 10h18" />
          </svg>
        </span>
      </div>
      {/* 투명 네이티브 date 입력을 박스 위에 겹쳐, 모바일에서 탭하면 OS 날짜
          선택기가 바로 열리도록 한다(showPicker 미지원/iOS에서도 안정적). */}
      <input
        ref={inputRef}
        id={id}
        type="date"
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onClick={openPicker}
        className={`absolute inset-0 h-full w-full opacity-0 ${
          disabled ? "pointer-events-none cursor-not-allowed" : "cursor-pointer"
        }`}
      />
    </div>
  );
};

interface PetFormProps {
  form: PetFormState;
  errors: PetFormErrors;
  isDetailMode: boolean;
  customSpeciesInputRef: RefObject<HTMLInputElement>;
  updateForm: <Key extends keyof PetFormState>(
    key: Key,
    value: PetFormState[Key],
  ) => void;
  handleNameChange: (event: ChangeEvent<HTMLInputElement>) => void;
  handleNotesChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
}

const PetForm = ({
  form,
  errors,
  isDetailMode,
  customSpeciesInputRef,
  updateForm,
  handleNameChange,
  handleNotesChange,
}: PetFormProps) => {
  const { t, lang } = useTranslation();
  const speciesLabel = (value: string) =>
    ({ "강아지": t("pet.speciesDog"), "고양이": t("pet.speciesCat"), "기타": t("pet.speciesOther") })[value] || value;
  const genderLabel = (value: string) =>
    ({ "수컷": t("pet.genderMale"), "암컷": t("pet.genderFemale"), "모름": t("pet.unknown") })[value] || value;
  const neuteredLabel = (value: string) =>
    ({ "예": t("pet.yes"), "아니오": t("pet.no"), "모름": t("pet.unknown") })[value] || value;

  return (
    <>
      <section className="px-1 md:px-2 mt-4 md:mt-6">
        <div className="mb-4 flex items-center gap-2 text-slate-900">
          <h2 className="text-lg md:text-xl font-extrabold tracking-tight">{t("pet.basicInfo")}</h2>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label htmlFor="petname" className={labelClass}>
              {t("pet.nameLabel")}
              <RequiredMark />
            </label>
            <input
              id="petname"
              value={form.petname}
              onChange={handleNameChange}
              readOnly={isDetailMode}
              placeholder={t("pet.namePlaceholder")}
              className={`${inputClass} ${
                errors.petname ? errorInputClass : ""
              } ${isDetailMode ? "bg-slate-50" : ""}`}
            />
            <FieldError message={errors.petname} />
          </div>

          <div>
            <label htmlFor="gender" className={labelClass}>
              {t("pet.genderLabel")}
              <RequiredMark />
            </label>
            <select
              id="gender"
              value={form.gender}
              disabled={isDetailMode}
              onChange={(event) => updateForm("gender", event.target.value)}
              className={`${selectClass} ${
                errors.gender ? errorInputClass : ""
              } ${isDetailMode ? "bg-slate-50" : ""}`}
            >
              <option value="">{t("pet.selectPlaceholder")}</option>
              {genderOptions.map((option) => (
                <option key={option} value={option}>
                  {genderLabel(option)}
                </option>
              ))}
            </select>
            <FieldError message={errors.gender} />
          </div>

          <div>
            <label htmlFor="weight" className={labelClass}>
              {t("pet.weightLabel")}
              <RequiredMark />
            </label>
            <div className="relative">
              <input
                id="weight"
                type="number"
                min="0"
                step="0.1"
                value={form.weight}
                readOnly={isDetailMode}
                onChange={(event) => updateForm("weight", event.target.value)}
                placeholder={t("pet.weightPlaceholder")}
                className={`${inputClass} pr-12 ${
                  errors.weight ? errorInputClass : ""
                } ${isDetailMode ? "bg-slate-50" : ""}`}
              />
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-sm font-extrabold text-slate-500">
                kg
              </span>
            </div>
            <FieldError message={errors.weight} />
          </div>

          <div>
            <label htmlFor="is-neutered" className={labelClass}>
              {t("pet.neuteredLabel")}
              <RequiredMark />
            </label>
            <select
              id="is-neutered"
              value={form.isNeutered}
              disabled={isDetailMode}
              onChange={(event) =>
                updateForm("isNeutered", event.target.value)
              }
              className={`${selectClass} ${
                errors.isNeutered ? errorInputClass : ""
              } ${isDetailMode ? "bg-slate-50" : ""}`}
            >
              <option value="">{t("pet.selectPlaceholder")}</option>
              {neuteredOptions.map((option) => (
                <option key={option} value={option}>
                  {neuteredLabel(option)}
                </option>
              ))}
            </select>
            <FieldError message={errors.isNeutered} />
          </div>
        </div>
      </section>

      <section className="px-1 md:px-2 mt-6 md:mt-8">

        <div>
          <label className={labelClass}>
            {t("pet.speciesLabel")}
            <RequiredMark />
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            {speciesOptions.map((option) => (
              <div
                key={option}
                className={getChoiceClass(
                  form.species === option,
                  option === "기타" ? "teal" : "slate",
                )}
                onClick={() => {
                  if (isDetailMode) return;
                  updateForm("species", option);
                  if (option !== "기타") {
                    updateForm("customSpecies", "");
                  } else {
                    setTimeout(() => customSpeciesInputRef.current?.focus(), 50);
                  }
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    if (!isDetailMode) {
                      updateForm("species", option);
                    }
                  }
                }}
              >
                {option === "기타" && form.species === "기타" ? (
                  <div className="flex h-full w-full items-center justify-center animate-in fade-in zoom-in duration-200">
                    <input
                      ref={customSpeciesInputRef}
                      value={form.customSpecies}
                      disabled={isDetailMode}
                      onChange={(event) =>
                        updateForm("customSpecies", event.target.value)
                      }
                      onClick={(e) => e.stopPropagation()}
                      placeholder={t("pet.customSpeciesPlaceholder")}
                      className={`h-full w-full bg-transparent px-2 text-center text-sm font-extrabold text-[#1F2937] outline-none placeholder:text-[#6B7280] ${
                        errors.customSpecies ? "ring-2 ring-red-400 rounded-lg" : ""
                      }`}
                    />
                  </div>
                ) : (
                  <div className="flex items-center justify-center gap-2">
                    {option !== "기타" && (
                      <span className="text-xl transition-transform duration-300 group-hover:scale-110">
                        {option === "강아지" ? "🐶" : "🐱"}
                      </span>
                    )}
                    <span className="font-extrabold text-sm">{speciesLabel(option)}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
          <FieldError message={errors.species || errors.customSpecies} />
        </div>

        <div className="mt-4">
          <label htmlFor="breed" className={labelClass}>
            {t("pet.breedLabel")}
          </label>
          <input
            id="breed"
            value={form.breed}
            readOnly={isDetailMode}
            onChange={(event) => updateForm("breed", event.target.value)}
            placeholder={t("pet.breedPlaceholder")}
            className={`${inputClass} ${isDetailMode ? "bg-slate-50" : ""}`}
          />
        </div>
      </section>

      <section className="px-1 md:px-2 mt-8 md:mt-10 mb-6 md:mb-8">
        <div className="mb-4 flex items-center gap-2 text-slate-900">
          <h2 className="text-lg md:text-xl font-extrabold tracking-tight">{t("pet.healthInfo")}</h2>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label htmlFor="birth-date" className={labelClass}>
              {t("pet.birthDate")}
            </label>
            <LocalizedDateInput
              id="birth-date"
              value={form.birthDate}
              disabled={isDetailMode || form.isBirthUnknown}
              label={t("pet.datePlaceholder")}
              lang={lang}
              onChange={(value) => updateForm("birthDate", value)}
            />
            {form.birthDate && !form.isBirthUnknown ? (
              <p className="mt-1 text-xs font-bold text-slate-500">
                {t("pet.selectedDate", { date: formatDatePreview(form.birthDate, lang) })}
              </p>
            ) : null}
            <label className="mt-3 flex items-center gap-2 text-sm font-semibold text-slate-600">
              <input
                type="checkbox"
                checked={form.isBirthUnknown}
                disabled={isDetailMode}
                onChange={(event) => {
                  updateForm("isBirthUnknown", event.target.checked);
                  if (event.target.checked) {
                    updateForm("birthDate", "");
                  }
                }}
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
              />
              {t("pet.birthUnknown")}
            </label>
          </div>

          <div>
            <label htmlFor="checkup-date" className={labelClass}>
              {t("pet.lastCheckup")}
            </label>
            <LocalizedDateInput
              id="checkup-date"
              value={form.checkupDate}
              disabled={isDetailMode || form.isCheckupUnknown}
              label={t("pet.datePlaceholder")}
              lang={lang}
              onChange={(value) => updateForm("checkupDate", value)}
            />
            {form.checkupDate && !form.isCheckupUnknown ? (
              <p className="mt-1 text-xs font-bold text-slate-500">
                {t("pet.selectedDate", { date: formatDatePreview(form.checkupDate, lang) })}
              </p>
            ) : null}
            <label className="mt-3 flex items-center gap-2 text-sm font-semibold text-slate-600">
              <input
                type="checkbox"
                checked={form.isCheckupUnknown}
                disabled={isDetailMode}
                onChange={(event) => {
                  updateForm("isCheckupUnknown", event.target.checked);
                  if (event.target.checked) {
                    updateForm("checkupDate", "");
                  }
                }}
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
              />
              {t("pet.checkupUnknown")}
            </label>
          </div>

          <div className="md:col-span-2">
            <div className="flex items-center justify-between">
              <label htmlFor="notes" className={labelClass}>
                {t("pet.notesLabel")}
              </label>
            </div>
            <div className="relative">
              <textarea
                id="notes"
                value={form.notes}
                readOnly={isDetailMode}
                onChange={handleNotesChange}
                placeholder={t("pet.notesPlaceholder")}
                className={`h-24 w-full resize-none rounded-xl bg-[#F8FAFC] px-4 py-3 pb-8 text-sm font-semibold leading-relaxed text-[#1F2937] outline-none transition-all duration-300 placeholder:text-[#6B7280] border border-[#E5E7EB] focus:border-[#2F6F67] focus:bg-white focus:ring-4 focus:ring-[#2F6F67]/10 hover:border-[#6B7280]/30 ${
                  isDetailMode ? "bg-slate-100" : ""
                }`}
              />
              <span className="absolute bottom-3 right-4 text-xs font-bold text-[#6B7280]">
                {form.notes.length} / {maxNotesLength}
              </span>
            </div>
          </div>
        </div>
      </section>
    </>
  );
};

export default PetForm;
