import axios, { AxiosError } from "axios";
import { API_BASE_URL, apiClient } from "./client";

export interface HospitalUser {
  id: string;
  name: string;
  hospitalName: string;
  role: "HOSPITAL_ADMIN" | "VETERINARIAN";
  isFirstLogin: boolean;
  licenseNumber?: string;
  hospitalPhone?: string;
  businessNumber?: string;
}

export interface AuthSession {
  accessToken: string;
  refreshToken: string;
  user: HospitalUser;
  lastLoginAt?: string;
}

interface DoctorLoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  is_initial_password: boolean;
  hospital_name?: string;
  doctor_name?: string;
  license_number?: string;
  hospital_number?: string;
  business_number?: string;
}

interface PasswordChangeResponse {
  code: number;
  message: string;
}

const SESSION_STORAGE_KEY = "medipaw_vet_session";
const PASSWORD_CHANGED_USERS_STORAGE_KEY = "medipaw_vet_password_changed_users";

export async function changePassword(params: {
  accessToken: string;
  currentPassword: string;
  newPassword: string;
  newPasswordConfirm: string;
}) {
  try {
    const { data } = await apiClient.put<PasswordChangeResponse>(
      "/doctor/auth/password/change",
      {
        current_password: params.currentPassword,
        new_password: params.newPassword,
        new_password_confirm: params.newPasswordConfirm,
      },
      {
        headers: { Authorization: `Bearer ${params.accessToken}` },
      }
    );

    if (data.code !== 200) {
      throw new Error(data.message ?? "비밀번호 변경에 실패했습니다.");
    }
  } catch (err) {
    throw new Error(
      getApiErrorMessage(err, "비밀번호 변경 중 오류가 발생했습니다.")
    );
  }
}

export function getSavedSession(): AuthSession | null {
  const savedSession = localStorage.getItem(SESSION_STORAGE_KEY);

  if (!savedSession) {
    return null;
  }

  try {
    const parsedSession = JSON.parse(savedSession) as AuthSession;

    if (hasChangedPassword(parsedSession.user.id)) {
      return {
        ...parsedSession,
        user: {
          ...parsedSession.user,
          isFirstLogin: false,
        },
      };
    }

    return parsedSession;
  } catch {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

export function saveSession(session: AuthSession) {
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function clearSession() {
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

export async function loginDoctor(loginid: string, password: string) {
  try {
    const { data } = await apiClient.post<DoctorLoginResponse>("/doctor/auth/login", {
      loginid,
      password,
    });

    const session: AuthSession = {
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      lastLoginAt: new Date().toISOString(),
      user: {
        id: loginid,
        name: data.doctor_name ?? data.hospital_name ?? loginid,
        hospitalName: data.hospital_name ?? loginid,
        role: "HOSPITAL_ADMIN",
        isFirstLogin: data.is_initial_password,
        licenseNumber: data.license_number,
        hospitalPhone: data.hospital_number,
        businessNumber: data.business_number,
      },
    };

    if (hasChangedPassword(session.user.id)) {
      session.user.isFirstLogin = false;
    }

    saveSession(session);
    return session;
  } catch (err) {
    throw new Error(getApiErrorMessage(err, "로그인 중 오류가 발생했습니다."));
  }
}

export async function changeFirstPassword(params: {
  accessToken: string;
  currentPassword: string;
  newPassword: string;
  newPasswordConfirm: string;
  session: AuthSession;
}) {
  try {
    const { data } = await apiClient.put<PasswordChangeResponse>(
      "/doctor/auth/password/change",
      {
        current_password: params.currentPassword,
        new_password: params.newPassword,
        new_password_confirm: params.newPasswordConfirm,
      },
      {
        headers: {
          Authorization: `Bearer ${params.accessToken}`,
        },
      }
    );

    if (data.code !== 200) {
      throw new Error(data.message);
    }

    const session: AuthSession = {
      ...params.session,
      accessToken: params.accessToken,
      user: {
        ...params.session.user,
        isFirstLogin: false,
      },
    };

    markPasswordChanged(params.session.user.id);
    saveSession(session);

    return session;
  } catch (err) {
    throw new Error(
      getApiErrorMessage(err, "비밀번호 변경 중 오류가 발생했습니다.")
    );
  }
}

function hasChangedPassword(userId: string) {
  return getChangedPasswordUserIds().includes(userId);
}

function markPasswordChanged(userId: string) {
  const changedUserIds = getChangedPasswordUserIds();

  if (changedUserIds.includes(userId)) {
    return;
  }

  localStorage.setItem(
    PASSWORD_CHANGED_USERS_STORAGE_KEY,
    JSON.stringify([...changedUserIds, userId])
  );
}

function getChangedPasswordUserIds() {
  const savedUserIds = localStorage.getItem(PASSWORD_CHANGED_USERS_STORAGE_KEY);

  if (!savedUserIds) {
    return [];
  }

  try {
    const parsedUserIds = JSON.parse(savedUserIds);
    return Array.isArray(parsedUserIds)
      ? parsedUserIds.filter((userId): userId is string => typeof userId === "string")
      : [];
  } catch {
    localStorage.removeItem(PASSWORD_CHANGED_USERS_STORAGE_KEY);
    return [];
  }
}

export function isPasswordPolicyValid(password: string, userId: string) {
  const hasValidLength = password.length >= 8 && password.length <= 20;
  const hasLetter = /[A-Za-z]/.test(password);
  const hasNumber = /\d/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const isDifferentFromId = password !== userId;
  const hasNoRepeatedChars = !/(.)\1\1/.test(password);
  const hasNoSequentialChars = !hasSequentialChars(password);

  return (
    hasValidLength &&
    hasLetter &&
    hasNumber &&
    hasSpecial &&
    isDifferentFromId &&
    hasNoRepeatedChars &&
    hasNoSequentialChars
  );
}

export function getPasswordPolicyStatus(password: string, userId: string) {
  return [
    {
      label: "8자 이상 20자 이하",
      isValid: password.length >= 8 && password.length <= 20,
    },
    {
      label: "영문, 숫자, 특수문자 포함",
      isValid:
        /[A-Za-z]/.test(password) &&
        /\d/.test(password) &&
        /[^A-Za-z0-9]/.test(password),
    },
    {
      label: "기존 비밀번호 및 최근 사용 비밀번호 재사용 불가",
      isValid: password.length > 0,
    },
    {
      label: "동일 문자 3회 이상 및 연속 문자 사용 불가",
      isValid:
        password.length > 0 &&
        !/(.)\1\1/.test(password) &&
        !hasSequentialChars(password),
    },
    {
      label: "아이디와 동일한 비밀번호 사용 불가",
      isValid: password.length > 0 && password !== userId,
    },
  ];
}

export async function resetPasswordByLicense(loginid: string, licenseNumber: string): Promise<string> {
  const res = await axios.post(`${API_BASE_URL}/doctor/auth/reset-password`, {
    loginid,
    license_number: licenseNumber,
  });
  const data = res.data;
  return data.result?.temp_password ?? data.temp_password ?? data.data?.temp_password;
}

function getApiErrorMessage(err: unknown, fallbackMessage: string) {
  if (!axios.isAxiosError(err)) {
    return err instanceof Error ? err.message : fallbackMessage;
  }

  const axiosError = err as AxiosError<{
    message?: string;
    detail?: string;
    error?: string;
  }>;

  if (axiosError.code === "ECONNABORTED") {
    return `요청 시간이 초과되었습니다. ${API_BASE_URL} 연결 상태를 확인해주세요.`;
  }

  if (!axiosError.response) {
    return `백엔드 서버에 연결할 수 없습니다. ${API_BASE_URL} 서버가 실행 중인지 확인해주세요.`;
  }

  return (
    axiosError.response?.data?.message ??
    axiosError.response?.data?.detail ??
    axiosError.response?.data?.error ??
    fallbackMessage
  );
}

function hasSequentialChars(password: string) {
  const normalized = password.toLowerCase();

  for (let index = 0; index < normalized.length - 2; index += 1) {
    const first = normalized.charCodeAt(index);
    const second = normalized.charCodeAt(index + 1);
    const third = normalized.charCodeAt(index + 2);

    if (second === first + 1 && third === second + 1) {
      return true;
    }

    if (second === first - 1 && third === second - 1) {
      return true;
    }
  }

  return false;
}
