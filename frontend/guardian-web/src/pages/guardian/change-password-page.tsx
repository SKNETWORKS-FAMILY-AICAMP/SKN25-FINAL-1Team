import { type ChangeEvent, type FormEvent, useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { Link } from "react-router-dom";

import { changeMyPassword } from "../../api/user-api";
import ActionButton from "../../components/common/action-button";
import PageHeader from "../../components/common/page-header";
import SectionCard from "../../components/common/section-card";
import GuardianLayout from "../../layouts/guardian-layout";
import { useTranslation } from "../../i18n/language-context";

interface ApiMessageResponse {
  code?: number;
  message?: string;
}

interface PasswordForm {
  current_password: string;
  new_password: string;
  new_password_confirm: string;
}

type PasswordFieldErrors = Partial<Record<keyof PasswordForm, string>>;

const initialForm: PasswordForm = {
  current_password: "",
  new_password: "",
  new_password_confirm: "",
};

const inputClassName = (hasError?: boolean) =>
  [
    "mt-2 h-12 w-full rounded-xl border bg-white px-4 text-base text-slate-950 outline-none transition placeholder:text-slate-400 focus:ring-4",
    hasError
      ? "border-red-400 focus:border-red-500 focus:ring-red-100"
      : "border-slate-200 focus:border-blue-500 focus:ring-blue-100",
  ].join(" ");

const getErrorMessage = (error: unknown, fallbackMessage: string) => {
  if (isAxiosError<ApiMessageResponse | string>(error)) {
    const responseData = error.response?.data;

    if (typeof responseData === "string") {
      try {
        return (
          (JSON.parse(responseData) as ApiMessageResponse).message ||
          fallbackMessage
        );
      } catch {
        return fallbackMessage;
      }
    }

    return responseData?.message || fallbackMessage;
  }

  return fallbackMessage;
};

const ChangePasswordPage = () => {
  const { t } = useTranslation();
  const [form, setForm] = useState<PasswordForm>(initialForm);
  const [fieldErrors, setFieldErrors] = useState<PasswordFieldErrors>({});
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isNewPasswordValid = useMemo(
    () =>
      /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$/.test(
        form.new_password,
      ),
    [form.new_password],
  );

  const handleChange =
    (field: keyof PasswordForm) =>
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
      setMessage("");
    };

  const validateForm = () => {
    const nextErrors: PasswordFieldErrors = {};

    if (!form.current_password) {
      nextErrors.current_password = t("changePassword.currentRequired");
    }

    if (!isNewPasswordValid) {
      nextErrors.new_password = t("changePassword.passwordHelper");
    }

    if (!form.new_password_confirm) {
      nextErrors.new_password_confirm = t("changePassword.confirmRequired");
    } else if (form.new_password !== form.new_password_confirm) {
      nextErrors.new_password_confirm = t("changePassword.mismatch");
    }

    return nextErrors;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const nextErrors = validateForm();
    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors);
      return;
    }

    try {
      setIsSubmitting(true);
      setMessage("");

      const response = await changeMyPassword(form);

      setForm(initialForm);
      setFieldErrors({});
      setMessageType("success");
      setMessage(response.message || t("changePassword.success"));
    } catch (error) {
      setMessageType("error");
      setMessage(getErrorMessage(error, t("changePassword.failed")));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <GuardianLayout>
      <PageHeader
        title={t("changePassword.title")}
        description={t("changePassword.description")}
      />

      <SectionCard>
        <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label
                className="text-sm font-bold text-slate-800"
                htmlFor="current_password"
              >
                {t("changePassword.currentLabel")}
              </label>
              <input
                id="current_password"
                type="password"
                autoComplete="current-password"
                value={form.current_password}
                onChange={handleChange("current_password")}
                aria-invalid={Boolean(fieldErrors.current_password)}
                className={inputClassName(Boolean(fieldErrors.current_password))}
              />
              {fieldErrors.current_password ? (
                <p className="mt-1.5 text-xs font-semibold text-red-500">
                  {fieldErrors.current_password}
                </p>
              ) : null}
            </div>

            <div>
              <label
                className="text-sm font-bold text-slate-800"
                htmlFor="new_password"
              >
                {t("changePassword.newLabel")}
              </label>
              <input
                id="new_password"
                type="password"
                autoComplete="new-password"
                value={form.new_password}
                onChange={handleChange("new_password")}
                aria-invalid={Boolean(fieldErrors.new_password)}
                className={inputClassName(Boolean(fieldErrors.new_password))}
              />
              <p
                className={[
                  "mt-1.5 text-xs font-semibold",
                  fieldErrors.new_password ? "text-red-500" : "text-slate-500",
                ].join(" ")}
              >
                {fieldErrors.new_password || t("changePassword.passwordHelper")}
              </p>
            </div>

            <div>
              <label
                className="text-sm font-bold text-slate-800"
                htmlFor="new_password_confirm"
              >
                {t("changePassword.confirmLabel")}
              </label>
              <input
                id="new_password_confirm"
                type="password"
                autoComplete="new-password"
                value={form.new_password_confirm}
                onChange={handleChange("new_password_confirm")}
                aria-invalid={Boolean(fieldErrors.new_password_confirm)}
                className={inputClassName(
                  Boolean(fieldErrors.new_password_confirm),
                )}
              />
              {fieldErrors.new_password_confirm ? (
                <p className="mt-1.5 text-xs font-semibold text-red-500">
                  {fieldErrors.new_password_confirm}
                </p>
              ) : null}
            </div>

            {message ? (
              <div
                className={[
                  "rounded-xl px-4 py-3 text-sm font-bold",
                  messageType === "success"
                    ? "bg-blue-50 text-blue-700"
                    : "bg-rose-50 text-rose-600",
                ].join(" ")}
              >
                {message}
              </div>
            ) : null}

            <div className="grid gap-3 pt-1 sm:grid-cols-2">
              <ActionButton
                type="submit"
                disabled={isSubmitting}
              >
                {isSubmitting ? t("changePassword.submitting") : t("changePassword.submit")}
              </ActionButton>
              <Link
                to="/mypage"
                className="inline-flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-6 text-sm font-extrabold text-slate-600 transition hover:bg-slate-50"
              >
                {t("changePassword.mypageCta")}
              </Link>
            </div>
          </form>
      </SectionCard>
    </GuardianLayout>
  );
};

export default ChangePasswordPage;
