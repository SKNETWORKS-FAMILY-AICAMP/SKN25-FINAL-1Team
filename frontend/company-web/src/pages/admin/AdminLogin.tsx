import { useState } from "react";
import { Link } from "react-router-dom";

import medipawSymbol from "../../../../shared/assets/logo/medipaw-symbol.png";

/**
 * 운영팀 로그인 (mock). 실제론 admin 인증 API 로 교체.
 * 데모에서는 아이디/비번 입력 후 로그인 시 통과한다.
 */
export default function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!loginId.trim() || !password.trim()) {
            setError("아이디와 비밀번호를 입력해 주세요.");
            return;
          }
          onLogin();
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

        <button type="submit" className="mp-btn-primary mt-5 w-full">
          로그인
        </button>
        <Link to="/" className="mt-3 block text-center text-xs font-bold text-slate-400 hover:text-slate-600">
          홈으로
        </Link>
      </form>
    </div>
  );
}
