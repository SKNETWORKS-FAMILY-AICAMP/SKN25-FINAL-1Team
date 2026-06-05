import React, { useState } from "react";
import { Eye, EyeOff, ShieldCheck, TriangleAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { AuthSession, loginDoctor } from "../../api/authApi";

interface LoginPageProps {
  onLoginSuccess: (session: AuthSession) => void;
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const navigate = useNavigate();
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [keepLogin, setKeepLogin] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const session = await loginDoctor(id, password);
      onLoginSuccess(session);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "로그인 중 오류가 발생했습니다."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className="mx-auto flex min-h-[560px] w-full max-w-[500px] flex-col rounded-lg border border-slate-200 bg-white px-10 py-10 shadow-sm">
        <div className="mb-10 h-[88px] text-center">
          <h2 className="text-3xl font-extrabold leading-tight text-slate-900">병원 관리자 로그인</h2>
          <p className="mt-4 text-sm font-bold text-slate-500">
            MediPaw 시스템에 로그인하세요.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="mb-2 block text-sm font-bold text-slate-700">
              아이디
            </label>
            <input
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="아이디를 입력하세요"
              className="h-14 w-full rounded-lg border border-slate-200 px-4 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-bold text-slate-700">
              비밀번호
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="비밀번호를 입력하세요"
                className="h-14 w-full rounded-lg border border-slate-200 px-4 pr-12 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400"
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-600">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-100">
                <TriangleAlert size={15} fill="currentColor" />
              </div>
              <p className="text-sm font-bold leading-6">{error}</p>
            </div>
          )}

          <label className="flex cursor-pointer items-center gap-3 text-sm font-semibold text-slate-500">
            <input
              type="checkbox"
              checked={keepLogin}
              onChange={(e) => setKeepLogin(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            로그인 상태 유지
          </label>

          <button
            type="submit"
            disabled={isLoading}
            className="h-14 w-full rounded-lg bg-blue-600 text-base font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {isLoading ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <div className="mt-7 flex items-center justify-center gap-5 text-sm font-bold text-blue-600">
          <button type="button" onClick={() => navigate("/account-inquiry")}>
            계정 문의
          </button>
          <span className="text-slate-300">|</span>
          <button type="button" onClick={() => navigate("/find-password")}>
            비밀번호 재설정
          </button>
        </div>
      </div>

      <div className="mx-auto mt-5 flex h-14 w-full max-w-[500px] items-center justify-center gap-3 rounded-lg bg-blue-50 text-sm font-bold text-blue-700">
        <ShieldCheck size={18} />
        계정 관련 문의는 담당 관리자에게 문의해주세요.
      </div>
    </AuthLayout>
  );
}
