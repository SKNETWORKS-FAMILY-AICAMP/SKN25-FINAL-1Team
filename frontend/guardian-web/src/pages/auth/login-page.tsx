import { ChangeEvent, FormEvent, useState } from "react";
import { isAxiosError } from "axios";
import { Link, useNavigate } from "react-router-dom";
import { MessageCircleMore, CalendarDays, ClipboardCheck, HeartPulse, Eye, EyeOff } from "lucide-react";

import { loginGuardian } from "../../api/auth-api";
import { useAuthStore } from "../../stores/auth-store";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

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
  {
    icon: MessageCircleMore,
    title: "AI 챗봇 상담",
    description: "반려동물 상태를 입력하면 필요한 상담 흐름을 안내합니다.",
  },
  {
    icon: CalendarDays,
    title: "병원 예약 및 관리",
    description: "상담 이후 필요한 병원 예약과 예약 내역을 관리할 수 있습니다.",
  },
  {
    icon: ClipboardCheck,
    title: "상담 후 예약 진행",
    description: "챗봇 상담 결과를 바탕으로 빠르게 예약 절차를 이어갑니다.",
  },
  {
    icon: HeartPulse,
    title: "상태 기록 및 경과 관리",
    description: "반려동물의 상태 변화와 상담 기록을 한곳에서 확인합니다.",
  },
];

const inputClassName = (hasError: boolean) =>
  [
    "mt-2 h-10 w-full rounded-xl border bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:ring-4",
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-100"
      : "border-slate-200 focus:border-blue-500 focus:ring-blue-100",
  ].join(" ");

const LoginPage = () => {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
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
      setErrorMessage("로그인 ID를 입력해주세요.");
      return;
    }

    if (!form.password) {
      setErrorMessage("비밀번호를 입력해주세요.");
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
        setErrorMessage(response.message || "로그인에 실패했습니다.");
        return;
      }

      setAuth({
        loginid: form.loginid.trim(),
        accessToken: response.result.access_token,
        refreshToken: response.result.refresh_token,
        remember: form.remember,
      });
      navigate("/home");
    } catch (error) {
      if (isAxiosError<LoginErrorResponse>(error)) {
        setErrorMessage(
          error.response?.data?.message ||
            "네트워크 오류가 발생했습니다. 다시 시도해주세요.",
        );
        return;
      }

      setErrorMessage("네트워크 오류가 발생했습니다. 다시 시도해주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-br from-sky-50 via-white to-blue-50 text-slate-900">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/login" className="flex items-center gap-3">
          <img src={medipawSymbol} alt="MediPaw" className="h-8 w-auto sm:h-9" />
        </Link>
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 content-start gap-6 px-4 pb-10 pt-8 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-stretch">
        <section className="flex flex-col justify-between gap-6">
          <div>
            <h1 className="text-4xl font-bold leading-tight text-slate-950">
              MediPaw와 함께
              <br />
              우리 아이의 건강을 지켜주세요
            </h1>
            <p className="mt-4 text-base leading-7 text-slate-600">
              AI 챗봇 상담으로 증상에 맞는 진료 예약을 도와드립니다.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            {serviceItems.map((item) => (
              <article
                key={item.title}
                className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 p-4"
              >
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white">
                  <item.icon className="h-6 w-6" />
                </span>
                <div>
                  <h2 className="text-base font-bold text-slate-900">{item.title}</h2>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    {item.description}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="flex flex-col justify-center rounded-3xl border border-blue-100 bg-white p-5 sm:p-6 lg:h-[34rem]">
          <div className="mb-4 text-center">
            <h2 className="text-2xl font-bold text-slate-950">로그인</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              MediPaw 계정으로 로그인해주세요.
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="loginid">
                ID
              </label>
              <input
                id="loginid"
                value={form.loginid}
                onChange={handleChange("loginid")}
                placeholder="ID를 입력해주세요."
                autoComplete="username"
                aria-invalid={Boolean(errorMessage && !form.loginid.trim())}
                className={inputClassName(Boolean(errorMessage && !form.loginid.trim()))}
              />
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="password">
                비밀번호
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={handleChange("password")}
                  placeholder="비밀번호를 입력해주세요."
                  autoComplete="current-password"
                  aria-invalid={Boolean(errorMessage && !form.password)}
                  className={`${inputClassName(
                    Boolean(errorMessage && !form.password),
                  )} pr-11`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 표시"}
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
                로그인 상태 유지
              </label>

              <div className="flex gap-3">
                <Link className="font-bold text-blue-600 hover:text-blue-700" to="/find-id">
                  아이디 찾기
                </Link>
                <Link
                  className="font-bold text-blue-600 hover:text-blue-700"
                  to="/find-password"
                >
                  비밀번호 찾기
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
              {isSubmitting ? "로그인 중..." : "로그인"}
            </button>

            <div className="flex items-center gap-3 py-1">
              <div className="h-px flex-1 bg-slate-200" />
              <span className="text-xs font-bold text-slate-400">또는</span>
              <div className="h-px flex-1 bg-slate-200" />
            </div>

            <Link
              to="/signup"
              className="flex h-11 w-full items-center justify-center rounded-xl border border-blue-500 text-sm font-bold text-blue-600 transition hover:bg-blue-50"
            >
              회원가입하기
            </Link>
          </form>
        </section>
      </main>

      <footer className="mx-auto flex w-full max-w-6xl flex-col gap-2 border-t border-blue-100 px-4 py-4 text-xs font-semibold text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>고객센터 02-123-4567 · aoj.medipaw@gmail.com · 평일 09:00 - 18:00</p>
        <p>© 2026 MediPaw. All rights reserved.</p>
      </footer>
    </div>
  );
};

export default LoginPage;
