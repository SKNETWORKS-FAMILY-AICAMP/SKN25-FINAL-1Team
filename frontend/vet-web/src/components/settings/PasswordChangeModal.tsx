import { useState } from "react";
import { CheckCircle2, LockKeyhole, TriangleAlert, X } from "lucide-react";
import {
  type AuthSession,
  changePassword,
  isPasswordPolicyValid,
  getPasswordPolicyStatus,
} from "../../api/authApi";
import { useEscapeToClose } from "../../hooks/useEscapeToClose";

interface Props {
  session: AuthSession;
  onClose: () => void;
}

export function PasswordChangeModal({ session, onClose }: Props) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const canSubmit =
    currentPassword.length > 0 &&
    newPassword.length > 0 &&
    confirmPassword.length > 0 &&
    !isLoading;

  const policyStatus = getPasswordPolicyStatus(newPassword, session.user.id);

  const handleClose = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError("");
    onClose();
  };

  useEscapeToClose(handleClose, !isLoading);

  const handleSubmit = async () => {
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
      await changePassword({
        accessToken: session.accessToken,
        currentPassword,
        newPassword,
        newPasswordConfirm: confirmPassword,
      });
      setSuccess(true);
      setTimeout(() => onClose(), 1800);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "비밀번호 변경 중 오류가 발생했습니다."
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-[480px] rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">비밀번호 변경</h2>
            <p className="mt-0.5 text-xs font-semibold text-slate-400">
              다시 사용하신 비밀번호를 입력해주세요.
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {success ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-50">
                <CheckCircle2 className="h-8 w-8 text-blue-600" />
              </div>
              <p className="text-base font-extrabold text-slate-800">비밀번호가 변경되었습니다.</p>
              <p className="text-sm font-semibold text-slate-400">잠시 후 자동으로 닫힙니다.</p>
            </div>
          ) : (
            <>
              <PasswordInputField
                label="현재 비밀번호"
                value={currentPassword}
                onChange={setCurrentPassword}
                placeholder="현재 비밀번호 입력"
              />
              <PasswordInputField
                label="새 비밀번호"
                value={newPassword}
                onChange={setNewPassword}
                placeholder="새 비밀번호 입력"
              />
              <PasswordInputField
                label="새 비밀번호 확인"
                value={confirmPassword}
                onChange={setConfirmPassword}
                placeholder="새 비밀번호 재입력"
              />

              {newPassword.length > 0 && (
                <ul className="rounded-lg bg-slate-50 px-4 py-3 space-y-1.5">
                  {policyStatus.map((p) => (
                    <li key={p.label} className="flex items-center gap-2 text-xs font-semibold">
                      <CheckCircle2
                        className={`h-3.5 w-3.5 shrink-0 ${p.isValid ? "text-blue-600" : "text-slate-300"}`}
                      />
                      <span className={p.isValid ? "text-slate-600" : "text-slate-300"}>
                        {p.label}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {error && (
                <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                  <p className="text-sm font-bold text-red-600">{error}</p>
                </div>
              )}
            </>
          )}
        </div>

        {!success && (
          <div className="flex justify-end gap-3 border-t border-slate-200 px-6 py-4">
            <button
              type="button"
              onClick={handleClose}
              className="h-10 rounded-lg border border-slate-200 px-5 text-sm font-extrabold text-slate-600 hover:bg-slate-100"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="h-10 rounded-lg bg-blue-600 px-5 text-sm font-extrabold text-white hover:bg-blue-700 disabled:bg-blue-200 disabled:cursor-not-allowed"
            >
              {isLoading ? "변경 중..." : "변경하기"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function PasswordInputField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-extrabold text-slate-600">{label}</label>
      <div className="relative">
        <LockKeyhole className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-12 w-full rounded-lg border border-slate-200 bg-white pl-10 pr-4 text-sm font-bold text-slate-800 outline-none transition placeholder:text-slate-300 focus:border-blue-300 focus:ring-2 focus:ring-blue-50"
        />
      </div>
    </div>
  );
}
