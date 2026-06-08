import { ChangeEvent, FormEvent, useState } from "react";
import { isAxiosError } from "axios";
import { Link } from "react-router-dom";
import { Lightbulb } from "lucide-react";

import { findGuardianPassword } from "../../api/auth-api";
import { useTranslation } from "../../i18n/language-context";
import AuthLanguageSelector from "../../components/auth-language-selector";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

interface FindPasswordFormState {
  loginid: string;
  name: string;
  phone: string;
}

interface FindPasswordErrorResponse {
  code?: number;
  message?: string;
}

const initialFormState: FindPasswordFormState = {
  loginid: "",
  name: "",
  phone: "",
};

const inputClassName = (hasError: boolean) =>
  [
    "h-10 w-full rounded-xl border bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:ring-4",
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

const FindPasswordPage = () => {
  const { t } = useTranslation();
  const [form, setForm] = useState<FindPasswordFormState>(initialFormState);
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange =
    (field: keyof FindPasswordFormState) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value =
        field === "phone"
          ? formatPhoneNumber(event.target.value)
          : event.target.value;

      setForm((current) => ({
        ...current,
        [field]: value,
      }));
      setTemporaryPassword("");
      setSuccessMessage("");
      setErrorMessage("");
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!form.loginid.trim()) {
      setErrorMessage(t("auth.findPassword.idRequired"));
      return;
    }

    if (!form.name.trim()) {
      setErrorMessage(t("auth.findPassword.nameRequired"));
      return;
    }

    if (!form.phone.trim()) {
      setErrorMessage(t("auth.findPassword.phoneRequired"));
      return;
    }

    if (!/^[0-9-]+$/.test(form.phone.trim())) {
      setErrorMessage(t("auth.phoneFormatInvalid"));
      return;
    }

    try {
      setIsSubmitting(true);
      setTemporaryPassword("");
      setSuccessMessage("");
      setErrorMessage("");

      const response = await findGuardianPassword({
        loginid: form.loginid.trim(),
        name: form.name.trim(),
        phone: form.phone.trim(),
      });

      if (response.code !== 200 || !response.result?.temp_password) {
        setErrorMessage(response.message || t("auth.notFound"));
        return;
      }

      setSuccessMessage(response.message || t("auth.findPassword.tempIssued"));
      setTemporaryPassword(response.result.temp_password);
    } catch (error) {
      if (isAxiosError<FindPasswordErrorResponse>(error)) {
        setErrorMessage(
          error.response?.data?.message || t("auth.networkError"),
        );
        return;
      }

      setErrorMessage(t("auth.networkError"));
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
              {t("auth.findPassword.title")}
            </h1>
            <p className="mt-4 text-base leading-7 text-slate-600">
              {t("auth.findPassword.heroSubtitleLine1")}
              <br />
              {t("auth.findPassword.heroSubtitleLine2")}
            </p>
          </div>

          <div className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 p-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white">
              <Lightbulb className="h-6 w-6" aria-hidden />
            </span>
            <div>
              <h2 className="text-base font-bold text-slate-900">{t("auth.infoTitle")}</h2>
              <ul className="mt-1 space-y-0.5 text-sm leading-snug text-slate-600">
                <li>{t("auth.findPassword.infoLine1")}</li>
                <li>{t("auth.findPassword.infoLine2")}</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="flex flex-col justify-center rounded-3xl border border-blue-100 bg-white p-5 sm:p-6 lg:h-[34rem]">
          <div className="mb-4 text-center">
            <h2 className="text-2xl font-bold text-slate-950">{t("auth.findPassword.title")}</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              {t("auth.findPassword.subtitle")}
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="loginid">
                {t("auth.idLabel")}
              </label>
              <input
                id="loginid"
                value={form.loginid}
                onChange={handleChange("loginid")}
                placeholder={t("auth.findPassword.idPlaceholder")}
                autoComplete="username"
                aria-invalid={Boolean(errorMessage && !form.loginid.trim())}
                className={inputClassName(Boolean(errorMessage && !form.loginid.trim()))}
              />
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="name">
                {t("auth.nameLabel")}
              </label>
              <input
                id="name"
                value={form.name}
                onChange={handleChange("name")}
                placeholder={t("auth.findPassword.namePlaceholder")}
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
                placeholder={t("auth.findPassword.phonePlaceholder")}
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

            {temporaryPassword && (
              <div className="rounded-2xl bg-blue-50 px-4 py-5 text-center">
                <p className="text-xs font-bold text-blue-600">{successMessage}</p>
                <p className="mt-2 text-xl font-extrabold text-blue-700">
                  {temporaryPassword}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  {t("auth.findPassword.tempLoginGuide")}
                </p>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="h-11 w-full rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {isSubmitting ? t("auth.findPassword.submitting") : t("auth.findPassword.submit")}
            </button>

            <div className="grid gap-3 sm:grid-cols-2">
              <Link
                to="/login"
                className="flex h-11 items-center justify-center rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700"
              >
                {t("auth.loginCta")}
              </Link>
              <Link
                to="/find-id"
                className="flex h-11 items-center justify-center rounded-xl border border-blue-500 text-sm font-bold text-blue-600 transition hover:bg-blue-50"
              >
                {t("auth.findPassword.findIdCta")}
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

export default FindPasswordPage;
