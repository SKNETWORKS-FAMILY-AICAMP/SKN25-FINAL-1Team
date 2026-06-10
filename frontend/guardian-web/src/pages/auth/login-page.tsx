import { ChangeEvent, FormEvent, useState } from "react";
import { isAxiosError } from "axios";
import { Link, useNavigate } from "react-router-dom";
import { MessageCircleMore, CalendarDays, ClipboardCheck, HeartPulse, Eye, EyeOff } from "lucide-react";

import { loginGuardian } from "../../api/auth-api";
import { getMyProfile } from "../../api/user-api";
import { useAuthStore } from "../../stores/auth-store";
import { useTranslation } from "../../i18n/language-context";
import AuthLanguageSelector from "../../components/auth-language-selector";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import { companyWebUrl } from "../../config/site";

interface LoginFormState {
  loginid: string;
  password: string;
  remember: boolean;
}

interface LoginErrorResponse {
  code?: number;
  message?: string;
}

const serviceItems = [
  { icon: MessageCircleMore, titleKey: "auth.serviceChatTitle", descKey: "auth.serviceChatDesc" },
  { icon: CalendarDays, titleKey: "auth.serviceBookTitle", descKey: "auth.serviceBookDesc" },
  { icon: ClipboardCheck, titleKey: "auth.serviceFlowTitle", descKey: "auth.serviceFlowDesc" },
  { icon: HeartPulse, titleKey: "auth.serviceRecordTitle", descKey: "auth.serviceRecordDesc" },
];

const inputClassName = (hasError: boolean) =>
  [
    "mt-2 h-10 w-full rounded-xl border bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:ring-4",
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-100"
      : "border-slate-200 focus:border-blue-500 focus:ring-blue-100",
  ].join(" ");

const LoginPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const updateGuardianProfile = useAuthStore(
    (state) => state.updateGuardianProfile,
  );
  const [form, setForm] = useState<LoginFormState>({
    loginid: "",
    password: "",
    remember: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleChange =
    (field: keyof Omit<LoginFormState, "remember">) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({
        ...current,
        [field]: event.target.value,
      }));
      setErrorMessage("");
    };

  const handleRememberChange = (event: ChangeEvent<HTMLInputElement>) => {
    setForm((current) => ({
      ...current,
      remember: event.target.checked,
    }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!form.loginid.trim()) {
      setErrorMessage(t("auth.login.idRequired"));
      return;
    }

    if (!form.password) {
      setErrorMessage(t("auth.login.passwordRequired"));
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMessage("");

      const response = await loginGuardian({
        loginid: form.loginid.trim(),
        password: form.password,
        keep_login: form.remember,
      });

      if (response.code !== 200 || !response.result) {
        setErrorMessage(response.message || t("auth.login.failed"));
        return;
      }

      setAuth({
        loginid: form.loginid.trim(),
        accessToken: response.result.access_token,
        refreshToken: response.result.refresh_token,
        remember: form.remember,
      });

      // 로그인 응답에는 이름이 없으므로 프로필을 조회해 보호자 이름을 채운다.
      // 실패해도 로그인 자체는 진행한다(이름은 마이페이지 진입 시 다시 보정됨).
      try {
        const profile = await getMyProfile();
        updateGuardianProfile({
          name: profile.name,
          phone: profile.phone,
        });
      } catch {
        // 프로필 조회 실패는 무시 — 네비게이션을 막지 않는다.
      }

      navigate("/home");
    } catch (error) {
      if (isAxiosError<LoginErrorResponse>(error)) {
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

      <main className="mx-auto grid w-full max-w-6xl flex-1 content-start gap-6 px-4 pb-10 pt-8 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-stretch">
        <section className="flex flex-col">
          <div>
            <h1 className="text-4xl font-bold leading-tight text-slate-950">
              {t("auth.heroTitleLine1")}
              <br />
              {t("auth.heroTitleLine2")}
            </h1>
            <p className="mt-4 whitespace-pre-line text-base leading-7 text-slate-600">
              {t("auth.heroSubtitle")}
            </p>
          </div>

          <div className="mt-10 flex flex-1 flex-col justify-between gap-3">
            {serviceItems.map((item) => (
              <article
                key={item.titleKey}
                className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 p-4"
              >
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#2a8587] text-white">
                  <item.icon className="h-6 w-6" />
                </span>
                <div>
                  <h2 className="text-base font-bold text-slate-900">{t(item.titleKey)}</h2>
                  <p className="mt-1 whitespace-pre-line text-[13px] leading-snug text-slate-600">
                    {t(item.descKey)}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="flex flex-col justify-center rounded-3xl border border-blue-100 bg-white p-5 sm:p-6 lg:min-h-[34rem]">
          <div className="mb-4 text-center">
            <h2 className="text-2xl font-bold text-slate-950">{t("auth.login.title")}</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              {t("auth.login.subtitle")}
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
                placeholder={t("auth.login.idPlaceholder")}
                autoComplete="username"
                aria-invalid={Boolean(errorMessage && !form.loginid.trim())}
                className={inputClassName(Boolean(errorMessage && !form.loginid.trim()))}
              />
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="password">
                {t("auth.passwordLabel")}
              </label>
              <div className="relative mt-2">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={handleChange("password")}
                  placeholder={t("auth.login.passwordPlaceholder")}
                  autoComplete="current-password"
                  aria-invalid={Boolean(errorMessage && !form.password)}
                  className={`${inputClassName(
                    Boolean(errorMessage && !form.password),
                  ).replace("mt-2 ", "")} pr-11`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? t("auth.login.hidePassword") : t("auth.login.showPassword")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-blue-600"
                >
                  {showPassword ? (
                    <EyeOff className="h-5 w-5" />
                  ) : (
                    <Eye className="h-5 w-5" />
                  )}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 text-sm">
              <label className="flex items-center gap-2 font-semibold text-slate-600">
                <input
                  type="checkbox"
                  checked={form.remember}
                  onChange={handleRememberChange}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                />
                {t("auth.login.remember")}
              </label>

              <div className="flex gap-3">
                <Link className="font-bold text-blue-600 hover:text-blue-700" to="/find-id">
                  {t("auth.login.findId")}
                </Link>
                <Link
                  className="font-bold text-blue-600 hover:text-blue-700"
                  to="/find-password"
                >
                  {t("auth.login.findPassword")}
                </Link>
              </div>
            </div>

            {errorMessage && (
              <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-sm font-bold text-red-600">
                {errorMessage}
              </p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="h-11 w-full rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {isSubmitting ? t("auth.login.submitting") : t("auth.login.submit")}
            </button>

            <div className="flex items-center gap-3 py-1">
              <div className="h-px flex-1 bg-slate-200" />
              <span className="text-xs font-bold text-slate-400">{t("auth.login.or")}</span>
              <div className="h-px flex-1 bg-slate-200" />
            </div>

            <Link
              to="/signup"
              className="flex h-11 w-full items-center justify-center rounded-xl border border-blue-500 text-sm font-bold text-blue-600 transition hover:bg-blue-50"
            >
              {t("auth.login.signupCta")}
            </Link>
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

export default LoginPage;
