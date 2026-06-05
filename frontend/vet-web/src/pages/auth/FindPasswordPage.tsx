import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { TriangleAlert } from "lucide-react";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { resetPasswordByLicense } from "../../api/authApi";

export default function FindPasswordPage() {
  const navigate = useNavigate();
  const [loginId, setLoginId] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      const password = await resetPasswordByLicense(loginId, licenseNumber);
      setTempPassword(password);
    } catch {
      setError("아이디 또는 면허번호가 일치하지 않습니다. 다시 확인해주세요.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className="mx-auto flex min-h-[560px] w-full max-w-[500px] flex-col rounded-lg border border-slate-200 bg-white px-10 py-10 shadow-sm">
        <div className="mb-12 h-[88px] text-center">
          <h2 className="text-3xl font-extrabold leading-tight text-slate-900">비밀번호 찾기</h2>
          <p className="mt-4 text-sm font-bold text-slate-500">
            등록된 의사 정보를 입력해주세요.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">
          <div>
            <label className="mb-2 block text-sm font-bold text-slate-700">
              아이디
            </label>
            <input
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              placeholder="아이디를 입력하세요"
              disabled={!!tempPassword}
              className="h-14 w-full rounded-lg border border-slate-200 px-4 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50 disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-bold text-slate-700">
              의사면허번호
            </label>
            <input
              value={licenseNumber}
              onChange={(e) => setLicenseNumber(e.target.value)}
              placeholder="면허번호를 입력하세요"
              disabled={!!tempPassword}
              className="h-14 w-full rounded-lg border border-slate-200 px-4 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50 disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>

          {error && (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-600">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-100">
                <TriangleAlert size={15} fill="currentColor" />
              </div>
              <p className="text-sm font-bold leading-6">{error}</p>
            </div>
          )}

          {tempPassword && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 px-5 py-4 text-center">
              <p className="text-sm font-bold text-blue-700">
                임시 비밀번호가 발급되었습니다.
              </p>
              <p className="mt-2 text-xl font-extrabold tracking-widest text-blue-600">
                {tempPassword}
              </p>
              <p className="mt-2 text-xs font-semibold text-blue-500">
                임시 비밀번호로 로그인한 후 비밀번호를 변경해주세요.
              </p>
            </div>
          )}

          {!tempPassword && (
            <button
              type="submit"
              disabled={isLoading || !loginId.trim() || !licenseNumber.trim()}
              className="h-14 w-full rounded-lg bg-blue-600 text-base font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {isLoading ? "확인 중..." : "임시 비밀번호 발급"}
            </button>
          )}
        </form>

        <div className="mt-7 grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => navigate("/login")}
            className="h-11 rounded-lg bg-blue-600 text-sm font-bold text-white transition hover:bg-blue-700"
          >
            로그인 하기
          </button>
          <button
            type="button"
            onClick={() => navigate("/account-inquiry")}
            className="h-11 rounded-lg border border-slate-200 text-sm font-bold text-slate-500 transition hover:bg-slate-50"
          >
            계정 문의
          </button>
        </div>
      </div>

      <div className="mx-auto mt-5 h-14 w-full max-w-[500px]" aria-hidden="true" />
    </AuthLayout>
  );
}
