import { ChangeEvent, FormEvent, useState } from "react";
import { isAxiosError } from "axios";
import { Link } from "react-router-dom";
import { Lightbulb } from "lucide-react";

import { findGuardianPassword } from "../../api/auth-api";
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
      setErrorMessage("ID를 입력해주세요.");
      return;
    }

    if (!form.name.trim()) {
      setErrorMessage("이름을 입력해주세요.");
      return;
    }

    if (!form.phone.trim()) {
      setErrorMessage("전화번호를 입력해주세요.");
      return;
    }

    if (!/^[0-9-]+$/.test(form.phone.trim())) {
      setErrorMessage("올바른 전화번호 형식으로 입력해주세요.");
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
        setErrorMessage(
          response.message || "입력하신 정보와 일치하는 계정을 찾을 수 없습니다.",
        );
        return;
      }

      setSuccessMessage(response.message || "임시 비밀번호가 발급되었습니다.");
      setTemporaryPassword(response.result.temp_password);
    } catch (error) {
      if (isAxiosError<FindPasswordErrorResponse>(error)) {
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
    <div className="flex min-h-screen flex-col bg-[#f3f6f0] text-slate-900">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/login" className="flex items-center gap-3">
          <img src={medipawSymbol} alt="MediPaw" className="h-8 w-auto sm:h-9" />
        </Link>
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 content-start gap-6 px-4 pb-10 pt-8 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
        <section className="space-y-14">
          <div>
            <h1 className="text-4xl font-bold leading-tight text-slate-950">
              비밀번호 찾기
            </h1>
            <p className="mt-4 text-base leading-7 text-slate-600">
              ID와 이름, 전화번호로
              <br />
              임시 비밀번호를 발급받을 수 있습니다.
            </p>
          </div>

          <div className="flex items-center gap-4 rounded-2xl border border-blue-100 bg-white/80 p-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white">
              <Lightbulb className="h-6 w-6" aria-hidden />
            </span>
            <div>
              <h2 className="text-base font-bold text-slate-900">안내사항</h2>
              <ul className="mt-1 space-y-0.5 text-sm leading-snug text-slate-600">
                <li>정보가 일치하면 임시 비밀번호가 발급됩니다.</li>
                <li>임시 비밀번호로 로그인한 뒤 새 비밀번호로 변경해주세요.</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="flex flex-col justify-center rounded-3xl border border-blue-100 bg-white p-5 sm:p-6 lg:h-[34rem]">
          <div className="mb-4 text-center">
            <h2 className="text-2xl font-bold text-slate-950">비밀번호 찾기</h2>
            <p className="mt-2 text-sm font-medium text-slate-500">
              등록된 보호자 정보를 입력해주세요.
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
              <label className="text-sm font-bold text-slate-800" htmlFor="name">
                이름
              </label>
              <input
                id="name"
                value={form.name}
                onChange={handleChange("name")}
                placeholder="이름을 입력해주세요."
                autoComplete="name"
                aria-invalid={Boolean(errorMessage && !form.name.trim())}
                className={inputClassName(Boolean(errorMessage && !form.name.trim()))}
              />
            </div>

            <div>
              <label className="text-sm font-bold text-slate-800" htmlFor="phone">
                전화번호
              </label>
              <input
                id="phone"
                value={form.phone}
                onChange={handleChange("phone")}
                placeholder="예: 010-1234-5678"
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
                  임시 비밀번호로 로그인한 후 비밀번호를 변경해주세요.
                </p>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="h-11 w-full rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {isSubmitting ? "발급 중..." : "임시 비밀번호 발급"}
            </button>

            <div className="grid gap-3 sm:grid-cols-2">
              <Link
                to="/login"
                className="flex h-11 items-center justify-center rounded-xl bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700"
              >
                로그인 하기
              </Link>
              <Link
                to="/find-id"
                className="flex h-11 items-center justify-center rounded-xl border border-blue-500 text-sm font-bold text-blue-600 transition hover:bg-blue-50"
              >
                아이디 찾기
              </Link>
            </div>
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

export default FindPasswordPage;
