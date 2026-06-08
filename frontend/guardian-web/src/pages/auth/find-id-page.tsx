import { ChangeEvent, FormEvent, useState } from "react";
import { isAxiosError } from "axios";
import { Link } from "react-router-dom";
import { Lightbulb } from "lucide-react";

import { findGuardianId } from "../../api/auth-api";
import { useTranslation } from "../../i18n/language-context";
import AuthLanguageSelector from "../../components/auth-language-selector";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

interface FindIdFormState {
  name: string;
  phone: string;
}

interface FindIdErrorResponse {
  code?: number;
  message?: string;
}

const initialFormState: FindIdFormState = {
  name: "",
  phone: "",
};

const inputClassName = (hasError: boolean) =>
  [
    "mt-2 h-10 w-full rounded-xl border bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:ring-4",
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-100"
      : "border-slate-200 focus:border-blue-500 focus:ring-blue-100",
  ].join(" ");

const formatPhoneNumber = (value: string) => {
  const digits = value.replace(/\D/g, "").slice(0, 11);

  if (digits.length < 4) {
    return digits;
  }

  if (digits.length < 8) {
    return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  }

  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
};

const FindIdPage = () => {
  const { t } = useTranslation();
  const [form, setForm] = useState<FindIdFormState>(initialFormState);
  const [foundLoginId, setFoundLoginId] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange =
    (field: keyof FindIdFormState) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value =
        field === "phone"
          ? formatPhoneNumber(event.target.value)
          : event.target.value;

      setForm((current) => ({
        ...current,
        [field]: value,
      }));
      setFoundLoginId("");
      setErrorMessage("");
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!form.name.trim()) {
      setErrorMessage(t("auth.findId.nameRequired"));
      return;
    }

    if (!form.phone.trim()) {
      setErrorMessage(t("auth.findId.phoneRequired"));
      return;
    }

    if (!/^[0-9-]+$/.test(form.phone.trim())) {
      setErrorMessage(t("auth.phoneFormatInvalid"));
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMessage("");
      setFoundLoginId("");

      const response = await findGuardianId({
        name: form.name.trim(),
        phone: form.phone.trim(),
      });

      if (response.code !== 200 || !response.result?.loginid) {
        setErrorMessage(response.message || t("auth.notFound"));
        return;
      }

      setFoundLoginId(response.result.loginid);
    } catch (error) {
      if (isAxiosError<FindIdErrorResponse>(error)) {
        setErrorMessage(
          error.response?.data?.message || t("auth.findId.failed"),
        );
        return;
      }

      setErrorMessage(t("auth.findId.failed"));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#f8fafc] text-slate-900">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/login" className="flex items-center gap-3">
          <img src={medipawSymbol} alt="MediPaw" className="h-8 w-auto sm:h-9" />
        </Link>
        <AuthLanguageSelector />
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 content-start gap-6 px-4 pb-10 pt-8 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
        <section className="space-y-14">
          <div>
            <h1 className="text-4xl font-bold leading-tight text-slate-950">
              {t("auth.findId.title")}
            </h1>
            <p className="mt-4 text-base leading-7 text-slate-600">
              {t("auth.findId.heroSubtitleLine1")}
              <br />
              {t("auth.findId.heroSubtitleLine2")}
            </p>
          </div>

          <div className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 p-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white">
              <Lightbulb className="h-6 w-6" aria-hidden />
            </span>
            <div>
              <h2 className="text-base font-bold text-slate-900">{t("auth.infoTitle")}</h2>
              <ul className="mt-1 space-y-0.5 whitespace-pre-line text-sm leading-snug text-slate-600">
                <li>{t("auth.findId.infoLine1")}</li>
                <li>{t("auth.findId.infoLine2")}</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="flex flex-col justify-center rounded-3xl border border-blue-100 bg-white p-5 sm:p-6 lg:h-[34rem]">
          <div className="mb-4 text-center">
            <h2 className="text-2xl font-bold text-slate-950">{t("auth.findId.title")}</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              {t("auth.findId.subtitle")}
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="name">
                {t("auth.nameLabel")}
              </label>
              <input
                id="name"
                value={form.name}
                onChange={handleChange("name")}
                placeholder={t("auth.findId.namePlaceholder")}
                autoComplete="name"
                aria-invalid={Boolean(errorMessage && !form.name.trim())}
                className={inputClassName(Boolean(errorMessage && !form.name.trim()))}
              />
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="phone">
                {t("auth.phoneLabel")}
              </label>
              <input
                id="phone"
                value={form.phone}
                onChange={handleChange("phone")}
                placeholder={t("auth.findId.phonePlaceholder")}
                autoComplete="tel"
                aria-invalid={Boolean(errorMessage && !form.phone.trim())}
                className={inputClassName(Boolean(errorMessage && !form.phone.trim()))}
              />
            </div>

            {errorMessage && (
              <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-sm font-bold text-red-600">
                {errorMessage}
              </p>
            )}

            {foundLoginId && (
              <div className="rounded-2xl bg-blue-50 px-4 py-5 text-center">
                <p className="text-xs font-bold text-blue-600">{t("auth.findId.foundLabel")}</p>
                <p className="mt-2 text-xl font-extrabold text-blue-700">
                  {foundLoginId}
                </p>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="h-11 w-full rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {isSubmitting ? t("auth.findId.submitting") : t("auth.findId.submit")}
            </button>

            <div className="grid gap-3 sm:grid-cols-2">
              <Link
                to="/login"
                className="flex h-11 items-center justify-center rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700"
              >
                {t("auth.loginCta")}
              </Link>
              <Link
                to="/find-password"
                className="flex h-11 items-center justify-center rounded-xl border border-blue-500 text-sm font-bold text-blue-600 transition hover:bg-blue-50"
              >
                {t("auth.findId.findPasswordCta")}
              </Link>
            </div>
          </form>
        </section>
      </main>

      <footer className="mx-auto flex w-full max-w-6xl flex-col gap-2 border-t border-blue-100 px-4 py-4 text-xs font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>{t("auth.footerContact")}</p>
        <p>{t("auth.footerCopyright")}</p>
      </footer>
    </div>
  );
};

export default FindIdPage;
