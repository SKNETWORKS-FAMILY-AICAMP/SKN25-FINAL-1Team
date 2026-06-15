import { useState } from "react";
import { Link } from "react-router-dom";

import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";
import { adminLogin } from "../../onboarding/api";

/** 운영팀 로그인 — 백엔드 /admin/login (JWT). */
export default function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!loginId.trim() || !password.trim()) {
            setError("아이디와 비밀번호를 입력해 주세요.");
            return;
          }
          setSubmitting(true);
          setError("");
          try {
            await adminLogin(loginId.trim(), password);
            onLogin();
          } catch (err) {
            setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
          } finally {
            setSubmitting(false);
          }
        }}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div className="flex flex-col items-center">
          <img src={medipawSymbol} alt="MediPaw" className="h-10 w-auto" />
          <h1 className="mt-4 text-xl font-black text-slate-900">운영팀 콘솔</h1>
          <p className="mt-1 text-sm font-semibold text-slate-500">관리자 전용</p>
        </div>

        <div className="mt-6 space-y-3">
          <input
            className="contact-input"
            placeholder="아이디"
            value={loginId}
            onChange={(e) => {
              setLoginId(e.target.value);
              setError("");
            }}
          />
          <input
            className="contact-input"
            type="password"
            placeholder="비밀번호"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError("");
            }}
          />
        </div>

        {error ? <p className="mt-3 text-xs font-bold text-rose-500">{error}</p> : null}

        <button type="submit" disabled={submitting} className="mp-btn-primary mt-5 w-full">
          {submitting ? "로그인 중…" : "로그인"}
        </button>
        <Link to="/" className="mt-3 block text-center text-xs font-bold text-slate-400 hover:text-slate-600">
          홈으로
        </Link>
      </form>
    </div>
  );
}
