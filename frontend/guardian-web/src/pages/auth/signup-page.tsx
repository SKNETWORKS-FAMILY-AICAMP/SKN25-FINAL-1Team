import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { Link, useNavigate } from "react-router-dom";
import { MessageCircleMore, CalendarDays, ClipboardCheck, HeartPulse } from "lucide-react";

import { signupGuardian } from "../../api/auth-api";
import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

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

const inputClassName = (hasError?: boolean) =>
  [
    "mt-2 h-10 w-full rounded-xl border bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:ring-4",
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-100"
      : "border-slate-200 focus:border-blue-500 focus:ring-blue-100",
  ].join(" ");

const helperClassName = (hasError?: boolean) =>
  [
    "mt-1.5 text-[11px] font-medium",
    hasError ? "text-red-500" : "text-slate-500",
  ].join(" ");

const getFallbackErrorMessage = (message?: string) =>
  message || "회원가입에 실패했습니다. 입력 정보를 확인하고 다시 시도해주세요.";

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
  const navigate = useNavigate();
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
      setForm((current) => ({
        ...current,
        [field]: event.target.value,
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
      nextFieldErrors.name = "이름을 입력해주세요.";
    } else if (form.name.trim().length > 30) {
      nextFieldErrors.name = "이름은 30자 이하로 입력해주세요.";
    }

    if (!isLoginIdValid) {
      nextFieldErrors.loginid =
        "영문과 숫자를 각각 1개 이상 포함해 4-20자로 입력해주세요.";
    }

    if (!isPhoneValid) {
      nextFieldErrors.phone = "010-1234-5678 형식의 휴대폰 번호를 입력해주세요.";
    }

    if (!isPasswordValid) {
      nextFieldErrors.password =
        "영문, 숫자, 특수문자를 포함해 8자 이상 입력해주세요.";
    }

    if (!form.passwordConfirm) {
      nextFieldErrors.passwordConfirm = "비밀번호 확인을 입력해주세요.";
    } else if (form.password !== form.passwordConfirm) {
      nextFieldErrors.passwordConfirm = "비밀번호가 일치하지 않습니다.";
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

      setSuccessMessage(response.message || "회원가입이 완료되었습니다. 로그인 화면으로 이동합니다.");
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
            <h2 className="text-2xl font-bold text-slate-950">보호자 회원가입</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              MediPaw 이용을 시작할 계정 정보를 입력해주세요.
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-sm font-bold text-slate-800" htmlFor="name">
                  이름
                </label>
                <input
                  id="name"
                  autoComplete="name"
                  value={form.name}
                  onChange={handleChange("name")}
                  placeholder="홍길동"
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
                  아이디
                </label>
                <input
                  id="loginid"
                  autoComplete="username"
                  value={form.loginid}
                  onChange={handleChange("loginid")}
                  placeholder="guardian123"
                  aria-invalid={Boolean(fieldErrors.loginid)}
                  className={inputClassName(Boolean(fieldErrors.loginid))}
                />
                <p className={helperClassName(Boolean(fieldErrors.loginid))}>
                  {fieldErrors.loginid || "영문·숫자 포함 4~20자로 입력해주세요."}
                </p>
              </div>
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="phone">
                휴대폰 번호
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
                {fieldErrors.phone || "본인 휴대폰 번호를 입력해주세요."}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label
                  className="text-sm font-bold text-slate-800"
                  htmlFor="password"
                >
                  비밀번호
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={handleChange("password")}
                  placeholder="비밀번호"
                  aria-invalid={Boolean(fieldErrors.password)}
                  className={inputClassName(Boolean(fieldErrors.password))}
                />
                <p className={helperClassName(Boolean(fieldErrors.password))}>
                  {fieldErrors.password || "영문·숫자·특수문자 포함 8자 이상 입력해주세요."}
                </p>
              </div>

              <div>
                <label
                  className="text-sm font-bold text-slate-800"
                  htmlFor="passwordConfirm"
                >
                  비밀번호 확인
                </label>
                <input
                  id="passwordConfirm"
                  type="password"
                  autoComplete="new-password"
                  value={form.passwordConfirm}
                  onChange={handleChange("passwordConfirm")}
                  placeholder="비밀번호 확인"
                  aria-invalid={Boolean(fieldErrors.passwordConfirm)}
                  className={inputClassName(Boolean(fieldErrors.passwordConfirm))}
                />
                <p className={helperClassName(Boolean(fieldErrors.passwordConfirm))}>
                  {fieldErrors.passwordConfirm || "동일한 비밀번호를 한 번 더 입력해주세요."}
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

            <button
              type="submit"
              disabled={isSubmitting}
              className="h-11 w-full rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {isSubmitting ? "가입 처리 중..." : "회원가입"}
            </button>

            <p className="text-center text-sm font-medium text-slate-500">
              이미 계정이 있으신가요?{" "}
              <Link to="/login" className="font-bold text-blue-600 hover:text-blue-700">
                로그인
              </Link>
            </p>
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

export default SignupPage;
