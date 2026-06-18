import axios, {
  AxiosHeaders,
  isAxiosError,
  type InternalAxiosRequestConfig,
} from "axios";

import { useAuthStore } from "../stores/auth-store";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? "/api";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 8000,
  headers: {
    "Content-Type": "application/json",
  },
});

interface RefreshTokenResponse {
  code: number;
  message: string;
  result?: {
    access_token: string;
  };
}

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

const authSkipUrls = ["/doctor/auth/login", "/doctor/auth/refresh"];
let refreshPromise: Promise<string> | null = null;

const isAuthSkipUrl = (url?: string) =>
  authSkipUrls.some((skipUrl) => url?.includes(skipUrl));

const setAuthorizationHeader = (
  config: InternalAxiosRequestConfig,
  token: string,
) => {
  if (config.headers instanceof AxiosHeaders) {
    config.headers.set("Authorization", `Bearer ${token}`);
    return;
  }
  config.headers = new AxiosHeaders(config.headers);
  config.headers.set("Authorization", `Bearer ${token}`);
};

const requestNewAccessToken = async (refreshToken: string) => {
  const response = await axios.post<RefreshTokenResponse>(
    `${API_BASE_URL}/doctor/auth/refresh`,
    { refresh_token: refreshToken },
    { headers: { "Content-Type": "application/json" } },
  );

  if (response.data.code !== 200 || !response.data.result?.access_token) {
    throw new Error(response.data.message || "세션이 만료되었습니다.");
  }

  return response.data.result.access_token;
};

const refreshAndRetryRequest = async (originalRequest: RetryableRequestConfig) => {
  if (originalRequest._retry || isAuthSkipUrl(originalRequest.url)) {
    return Promise.reject(new Error("Token refresh skipped."));
  }

  const { session, updateAccessToken, clearAuth } = useAuthStore.getState();

  if (!session?.refreshToken) {
    clearAuth();
    return Promise.reject(new Error("Refresh token is missing."));
  }

  try {
    originalRequest._retry = true;
    refreshPromise = refreshPromise ?? requestNewAccessToken(session.refreshToken);

    const accessToken = await refreshPromise;
    refreshPromise = null;
    updateAccessToken(accessToken);
    setAuthorizationHeader(originalRequest, accessToken);

    return apiClient(originalRequest);
  } catch (refreshError) {
    refreshPromise = null;
    clearAuth();
    return Promise.reject(refreshError);
  }
};

apiClient.interceptors.request.use((config) => {
  if (!config.headers?.Authorization) {
    const accessToken = useAuthStore.getState().session?.accessToken;
    if (accessToken && !isAuthSkipUrl(config.url)) {
      setAuthorizationHeader(config, accessToken);
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!isAxiosError(error)) {
      return Promise.reject(error);
    }

    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    const originalRequest = error.config as RetryableRequestConfig | undefined;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    if (originalRequest._retry || isAuthSkipUrl(originalRequest.url)) {
      return Promise.reject(error);
    }

    return refreshAndRetryRequest(originalRequest);
  },
);
