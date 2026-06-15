/**
 * 입점 신청 mock 스토어 (localStorage).
 *
 * /apply 에서 제출한 신청을 저장하고 /admin 에서 읽는다. 같은 브라우저 안에서
 * 신청 → 검토 → 발행 흐름을 백엔드 없이 데모할 수 있다.
 * 백엔드 API 가 준비되면 이 파일만 fetch 호출로 교체한다.
 */
import type { ApplicationStatus, HospitalApplication } from "./types";

const KEY = "medipaw.onboarding.applications";

function read(): HospitalApplication[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as HospitalApplication[]) : [];
  } catch {
    return [];
  }
}

function write(list: HospitalApplication[]): void {
  window.localStorage.setItem(KEY, JSON.stringify(list));
}

export function listApplications(): HospitalApplication[] {
  // 최신순
  return read().sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function getApplication(id: string): HospitalApplication | undefined {
  return read().find((a) => a.id === id);
}

export function addApplication(
  app: Omit<HospitalApplication, "id" | "status" | "createdAt">,
): HospitalApplication {
  const created: HospitalApplication = {
    ...app,
    id: `app_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    status: "접수",
    createdAt: new Date().toISOString(),
  };
  write([created, ...read()]);
  return created;
}

export function updateApplication(
  id: string,
  patch: Partial<HospitalApplication>,
): HospitalApplication | undefined {
  const list = read();
  const idx = list.findIndex((a) => a.id === id);
  if (idx === -1) return undefined;
  list[idx] = { ...list[idx], ...patch };
  write(list);
  return list[idx];
}

export function setStatus(
  id: string,
  status: ApplicationStatus,
  extra?: Partial<HospitalApplication>,
): HospitalApplication | undefined {
  return updateApplication(id, {
    status,
    reviewedAt: new Date().toISOString(),
    ...extra,
  });
}

/** 데모용 임시 비밀번호 생성. */
export function generateTempPassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
  return Array.from(
    { length: 10 },
    () => chars[Math.floor(Math.random() * chars.length)],
  ).join("");
}
