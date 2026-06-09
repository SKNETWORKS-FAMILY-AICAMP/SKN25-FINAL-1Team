import React, { useMemo, useState } from "react";
import {
  Eye,
  EyeOff,
  ShieldCheck,
  TriangleAlert,
  CheckCircle2,
} from "lucide-react";
import { AuthLayout } from "../../components/auth/AuthLayout";
import {
  AuthSession,
  changeFirstPassword,
  getPasswordPolicyStatus,
  isPasswordPolicyValid,
} from "../../api/authApi";

interface FirstPasswordChangePageProps {
  session: AuthSession;
  onPasswordChanged: (session: AuthSession) => void;
  onGoLogin: () => void;
}

export default function FirstPasswordChangePage({
  session,
  onPasswordChanged,
  onGoLogin,
}: FirstPasswordChangePageProps) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [visibleFields, setVisibleFields] = useState({
    current: false,
    next: false,
    confirm: false,
  });
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const policyStatus = useMemo(
    () => getPasswordPolicyStatus(newPassword, session.user.id),
    [newPassword, session.user.id]
  );
  const canSubmit =
    currentPassword.length > 0 &&
    newPassword.length > 0 &&
    confirmPassword.length > 0;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");

    if (newPassword !== confirmPassword) {
      setError("새 비밀번호와 확인 비밀번호가 일치하지 않습니다.");
      return;
    }

    if (currentPassword === newPassword) {
      setError("현재 비밀번호와 동일한 비밀번호는 사용할 수 없습니다.");
      return;
    }

    if (!isPasswordPolicyValid(newPassword, session.user.id)) {
      setError("비밀번호 정책을 모두 충족한 뒤 변경을 완료해주세요.");
      return;
    }

    setIsLoading(true);

    try {
      const changedSession = await changeFirstPassword({
        accessToken: session.accessToken,
        currentPassword,
        newPassword,
        newPasswordConfirm: confirmPassword,
        session,
      });
      onPasswordChanged(changedSession);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "비밀번호 변경 중 오류가 발생했습니다."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const toggleVisible = (field: keyof typeof visibleFields) => {
    setVisibleFields((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  return (
    <AuthLayout>
      <div className="mx-auto flex w-full max-w-[500px] flex-col rounded-lg border border-slate-200 bg-white px-10 py-10 shadow-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <ShieldCheck size={26} />
          </div>
          <h2 className="text-3xl font-extrabold leading-tight text-slate-900">
            비밀번호 변경
          </h2>
          <p className="mt-3 text-sm font-bold text-slate-500">
            첫 로그인 보안 설정 · {session.user.hospitalName}
          </p>
        </div>

        <div className="mb-5 flex items-start gap-3 rounded-lg bg-blue-50 px-4 py-3 text-blue-700">
          <ShieldCheck size={18} className="mt-0.5 shrink-0" />
          <p className="text-sm font-bold leading-6">
            계정 보안 강화를 위해 임시 비밀번호를 새 비밀번호로
            변경해야 시스템을 이용할 수 있습니다.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <PasswordField
            label="현재 비밀번호"
            value={currentPassword}
            visible={visibleFields.current}
            placeholder="현재 비밀번호를 입력하세요"
            onChange={setCurrentPassword}
            onToggleVisible={() => toggleVisible("current")}
          />

          <PasswordField
            label="새 비밀번호"
            value={newPassword}
            visible={visibleFields.next}
            placeholder="새 비밀번호를 입력하세요"
            onChange={setNewPassword}
            onToggleVisible={() => toggleVisible("next")}
          />

          <PasswordField
            label="새 비밀번호 확인"
            value={confirmPassword}
            visible={visibleFields.confirm}
            placeholder="새 비밀번호를 다시 입력하세요"
            onChange={setConfirmPassword}
            onToggleVisible={() => toggleVisible("confirm")}
          />

          {error && (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-600">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-100">
                <TriangleAlert size={15} fill="currentColor" />
              </div>
              <p className="text-sm font-bold leading-5">{error}</p>
            </div>
          )}

          {newPassword.length > 0 && (
            <ul className="rounded-lg bg-slate-50 px-5 py-4 space-y-1.5">
              <p className="mb-2 text-sm font-bold text-slate-700">비밀번호 정책</p>
              {policyStatus.map((policy) => (
                <li
                  key={policy.label}
                  className="flex items-center gap-2 text-sm font-semibold text-slate-600"
                >
                  <CheckCircle2
                    size={16}
                    className={
                      policy.isValid
                        ? "shrink-0 text-blue-600"
                        : "shrink-0 text-slate-300"
                    }
                  />
                  {policy.label}
                </li>
              ))}
            </ul>
          )}

          <button
            type="submit"
            disabled={!canSubmit || isLoading}
            className="h-14 w-full rounded-lg bg-blue-600 text-base font-bold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {isLoading ? "변경 중..." : "변경 완료"}
          </button>
        </form>

        <div className="mt-6 text-center">
          <button
            type="button"
            onClick={onGoLogin}
            className="text-sm font-bold text-slate-400 transition hover:text-slate-600"
          >
            첫 화면으로 돌아가기
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

interface PasswordFieldProps {
  label: string;
  value: string;
  visible: boolean;
  placeholder: string;
  onChange: (value: string) => void;
  onToggleVisible: () => void;
}

function PasswordField({
  label,
  value,
  visible,
  placeholder,
  onChange,
  onToggleVisible,
}: PasswordFieldProps) {
  return (
    <div>
      <label className="mb-2 block text-sm font-bold text-slate-700">
        {label}
      </label>
      <div className="relative">
        <input
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-14 w-full rounded-lg border border-slate-200 px-4 pr-12 text-sm font-medium outline-none transition placeholder:text-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
        />
        <button
          type="button"
          onClick={onToggleVisible}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-blue-600"
          aria-label={visible ? "비밀번호 숨기기" : "비밀번호 표시"}
        >
          {visible ? <EyeOff size={20} /> : <Eye size={20} />}
        </button>
      </div>
    </div>
  );
}
