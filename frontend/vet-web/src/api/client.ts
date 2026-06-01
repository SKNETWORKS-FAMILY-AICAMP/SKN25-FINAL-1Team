import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? "/api";

// authApi.ts 의 SESSION_STORAGE_KEY 와 동일해야 한다.
const SESSION_STORAGE_KEY = "medipaw_vet_session";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 8000,
  headers: {
    "Content-Type": "application/json",
  },
});

// 저장된 수의사 세션 토큰을 모든 요청에 자동 첨부한다.
// 호출부에서 Authorization 헤더를 직접 지정한 경우(dashboardApi/patientApi 등)는 그대로 둔다.
apiClient.interceptors.request.use((config) => {
  if (!config.headers?.Authorization) {
    try {
      const raw = localStorage.getItem(SESSION_STORAGE_KEY);
      const token = raw ? (JSON.parse(raw) as { accessToken?: string }).accessToken : null;
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // 세션 파싱 실패 시 토큰 없이 진행 (백엔드가 401 반환)
    }
  }
  return config;
});
