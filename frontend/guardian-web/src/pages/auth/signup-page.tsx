import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { Link, useNavigate } from "react-router-dom";
import { MessageCircleMore, CalendarDays, ClipboardCheck, HeartPulse } from "lucide-react";

import { signupGuardian } from "../../api/auth-api";
import { useTranslation } from "../../i18n/language-context";
import AuthLanguageSelector from "../../components/auth-language-selector";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import { companyWebUrl } from "../../config/site";

interface SignupFormState {
  name: string;
  loginid: string;
  phone: string;
  password: string;
  passwordConfirm: string;
}

type SignupFieldErrors = Partial<Record<keyof SignupFormState, string>>;

interface SignupErrorResponse {
  code?: number;
  message?: string;
}

const initialFormState: SignupFormState = {
  name: "",
  loginid: "",
  phone: "",
  password: "",
  passwordConfirm: "",
};

const serviceItems = [
  { icon: MessageCircleMore, titleKey: "auth.serviceChatTitle", descKey: "auth.serviceChatDesc" },
  { icon: ClipboardCheck, titleKey: "auth.serviceBookTitle", descKey: "auth.serviceBookDesc" },
  { icon: CalendarDays, titleKey: "auth.serviceFlowTitle", descKey: "auth.serviceFlowDesc" },
  { icon: HeartPulse, titleKey: "auth.serviceRecordTitle", descKey: "auth.serviceRecordDesc" },
];

const inputClassName = (hasError?: boolean) =>
  [
    "mt-2 h-10 w-full rounded-xl border bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:ring-4",
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-100"
      : "border-slate-200 focus:border-blue-500 focus:ring-blue-100",
  ].join(" ");

const helperClassName = (hasError?: boolean) =>
  [
    "mt-1.5 text-[11px] font-medium tracking-tighter whitespace-nowrap",
    hasError ? "text-red-500" : "text-slate-500",
  ].join(" ");

// 전화번호 입력 시 하이픈(-)을 자동으로 넣는다. 비밀번호 찾기 화면과 동일한 규칙.
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

const getApiFieldError = (message: string): SignupFieldErrors | null => {
  const lowerMessage = message.toLowerCase();

  if (lowerMessage.includes("loginid") || lowerMessage.includes("id")) {
    return { loginid: message };
  }

  if (lowerMessage.includes("password")) {
    return { password: message };
  }

  if (lowerMessage.includes("name")) {
    return { name: message };
  }

  if (lowerMessage.includes("phone")) {
    return { phone: message };
  }

  return null;
};

const SignupPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const getFallbackErrorMessage = (message?: string) =>
    message || t("auth.signup.failed");
  const [form, setForm] = useState<SignupFormState>(initialFormState);
  const [fieldErrors, setFieldErrors] = useState<SignupFieldErrors>({});
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isLoginIdValid = useMemo(
    () => /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{4,20}$/.test(form.loginid.trim()),
    [form.loginid],
  );

  const isPasswordValid = useMemo(
    () =>
      /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$/.test(form.password),
    [form.password],
  );

  const isPhoneValid = useMemo(
    () => /^01[016789]-?\d{3,4}-?\d{4}$/.test(form.phone.trim()),
    [form.phone],
  );

  const handleChange =
    (field: keyof SignupFormState) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value =
        field === "phone"
          ? formatPhoneNumber(event.target.value)
          : event.target.value;
      setForm((current) => ({
        ...current,
        [field]: value,
      }));
      setFieldErrors((current) => {
        const nextErrors = { ...current };
        delete nextErrors[field];
        return nextErrors;
      });
      setErrorMessage("");
      setSuccessMessage("");
    };

  const validateForm = () => {
    const nextFieldErrors: SignupFieldErrors = {};

    if (!form.name.trim()) {
      nextFieldErrors.name = t("auth.signup.nameRequired");
    } else if (form.name.trim().length > 30) {
      nextFieldErrors.name = t("auth.signup.nameTooLong");
    }

    if (!isLoginIdValid) {
      nextFieldErrors.loginid = t("auth.signup.idInvalid");
    }

    if (!isPhoneValid) {
      nextFieldErrors.phone = t("auth.signup.phoneInvalid");
    }

    if (!isPasswordValid) {
      nextFieldErrors.password = t("auth.signup.passwordInvalid");
    }

    if (!form.passwordConfirm) {
      nextFieldErrors.passwordConfirm = t("auth.signup.passwordConfirmRequired");
    } else if (form.password !== form.passwordConfirm) {
      nextFieldErrors.passwordConfirm = t("auth.signup.passwordMismatch");
    }

    return nextFieldErrors;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const nextFieldErrors = validateForm();
    if (Object.keys(nextFieldErrors).length > 0) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMessage("");

      const response = await signupGuardian({
        loginid: form.loginid.trim(),
        password: form.password,
        password_confirm: form.passwordConfirm,
        name: form.name.trim(),
        phone: form.phone.trim(),
      });

      if (response.code !== 200) {
        const message = getFallbackErrorMessage(response.message);
        const apiFieldError = getApiFieldError(message);

        if (apiFieldError) {
          setFieldErrors(apiFieldError);
          return;
        }

        setErrorMessage(message);
        return;
      }

      setSuccessMessage(response.message || t("auth.signup.success"));
      window.setTimeout(() => navigate("/login"), 800);
    } catch (error) {
      if (isAxiosError<SignupErrorResponse>(error)) {
        const statusCode = error.response?.data?.code ?? error.response?.status;
        const message = getFallbackErrorMessage(error.response?.data?.message);
        const apiFieldError = getApiFieldError(message);

        if (statusCode === 409) {
          setFieldErrors({ loginid: message });
          return;
        }

        if (apiFieldError) {
          setFieldErrors(apiFieldError);
          return;
        }

        setErrorMessage(message);
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

      <main className="mx-auto grid w-full max-w-6xl flex-1 content-start gap-6 px-4 pb-10 pt-8 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-stretch">
        <section className="flex flex-col justify-between">
          <div>
            <h1 className="text-4xl font-bold leading-tight text-slate-950">
              {t("auth.heroTitleLine1")}
              <br />
              {t("auth.heroTitleLine2")}
            </h1>
            <p className="mt-4 text-base leading-7 text-slate-600">
              {t("auth.heroSubtitle")}
            </p>
          </div>

          <div className="mt-6 flex flex-col gap-3">
            {serviceItems.map((item) => (
              <article
                key={item.titleKey}
                className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 px-4 py-3"
              >
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white">
                  <item.icon className="h-6 w-6" />
                </span>
                <div>
                  <h2 className="text-base font-bold text-slate-900">{t(item.titleKey)}</h2>
                  <p className="mt-1 whitespace-pre-line text-sm leading-snug text-slate-600">
                    {t(item.descKey)}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="flex flex-col rounded-3xl border border-blue-100 bg-white p-6 lg:p-8 lg:h-[34rem]">
          <div className="mb-8 text-center">
            <h2 className="text-2xl font-bold text-slate-950">{t("auth.signup.title")}</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              {t("auth.signup.subtitle")}
            </p>
          </div>

          <form className="space-y-3" onSubmit={handleSubmit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-sm font-bold text-slate-800" htmlFor="name">
                  {t("auth.signup.nameLabel")}
                </label>
                <input
                  id="name"
                  autoComplete="name"
                  value={form.name}
                  onChange={handleChange("name")}
                  placeholder={t("auth.signup.namePlaceholder")}
                  aria-invalid={Boolean(fieldErrors.name)}
                  className={inputClassName(Boolean(fieldErrors.name))}
                />
                {fieldErrors.name && (
                  <p className={helperClassName(true)}>{fieldErrors.name}</p>
                )}
              </div>

              <div>
                <label
                  className="text-sm font-bold text-slate-800"
                  htmlFor="loginid"
                >
                  {t("auth.signup.idLabel")}
                </label>
                <input
                  id="loginid"
                  autoComplete="username"
                  value={form.loginid}
                  onChange={handleChange("loginid")}
                  placeholder={t("auth.signup.idPlaceholder")}
                  aria-invalid={Boolean(fieldErrors.loginid)}
                  className={inputClassName(Boolean(fieldErrors.loginid))}
                />
                <p className={helperClassName(Boolean(fieldErrors.loginid))}>
                  {fieldErrors.loginid || t("auth.signup.idHelper")}
                </p>
              </div>
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="phone">
                {t("auth.signup.phoneLabel")}
              </label>
              <input
                id="phone"
                autoComplete="tel"
                inputMode="tel"
                value={form.phone}
                onChange={handleChange("phone")}
                placeholder="010-1234-5678"
                aria-invalid={Boolean(fieldErrors.phone)}
                className={inputClassName(Boolean(fieldErrors.phone))}
              />
              <p className={helperClassName(Boolean(fieldErrors.phone))}>
                {fieldErrors.phone || t("auth.signup.phoneHelper")}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label
                  className="text-sm font-bold text-slate-800"
                  htmlFor="password"
                >
                  {t("auth.signup.passwordLabel")}
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={handleChange("password")}
                  placeholder={t("auth.signup.passwordPlaceholder")}
                  aria-invalid={Boolean(fieldErrors.password)}
                  className={inputClassName(Boolean(fieldErrors.password))}
                />
                <p className={helperClassName(Boolean(fieldErrors.password))}>
                  {fieldErrors.password || t("auth.signup.passwordHelper")}
                </p>
              </div>

              <div>
                <label
                  className="text-sm font-bold text-slate-800"
                  htmlFor="passwordConfirm"
                >
                  {t("auth.signup.passwordConfirmLabel")}
                </label>
                <input
                  id="passwordConfirm"
                  type="password"
                  autoComplete="new-password"
                  value={form.passwordConfirm}
                  onChange={handleChange("passwordConfirm")}
                  placeholder={t("auth.signup.passwordConfirmPlaceholder")}
                  aria-invalid={Boolean(fieldErrors.passwordConfirm)}
                  className={inputClassName(Boolean(fieldErrors.passwordConfirm))}
                />
                <p className={helperClassName(Boolean(fieldErrors.passwordConfirm))}>
                  {fieldErrors.passwordConfirm || t("auth.signup.passwordConfirmHelper")}
                </p>
              </div>
            </div>

            {errorMessage && (
              <p className="rounded-2xl bg-red-50 px-4 py-3 text-center text-sm font-bold text-red-600">
                {errorMessage}
              </p>
            )}

            {successMessage && (
              <p className="rounded-2xl bg-blue-50 px-4 py-3 text-center text-sm font-bold text-blue-700">
                {successMessage}
              </p>
            )}

            <div className="flex flex-col gap-3">
              <div>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="h-12 w-full rounded-xl bg-blue-600 text-[15px] font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
                >
                  {isSubmitting ? t("auth.signup.submitting") : t("auth.signup.submit")}
                </button>
              </div>

              <p className="text-center text-sm font-medium text-slate-500">
                {t("auth.signup.hasAccount")}{" "}
                <Link to="/login" className="font-bold text-blue-600 hover:text-blue-700">
                  {t("auth.signup.loginLink")}
                </Link>
              </p>
            </div>
          </form>
        </section>
      </main>

      <footer className="mx-auto flex w-full max-w-6xl flex-col gap-2 border-t border-blue-100 px-4 py-4 text-xs font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>{t("auth.footerContact")}</p>
        <div className="flex items-center gap-4">
          <a
            href={companyWebUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="font-bold text-blue-600 transition hover:text-blue-700"
          >
            {t("auth.footerHome")}
          </a>
          <p>{t("auth.footerCopyright")}</p>
        </div>
      </footer>
    </div>
  );
};

export default SignupPage;
