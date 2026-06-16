import { create } from "zustand";

import {
  addMyHospital,
  getMyHospitals,
  removeMyHospital,
  setPrimaryHospital,
  type MyHospital,
} from "../api/hospital-api";

// 홈·병원탭·예약모달이 공유하는 "현재 병원" 단일 키. (기존 분산 localStorage 키 재사용)
const CURRENT_KEY = "medipaw.guardian.hospitalid";

type HospitalStatus = "idle" | "loading" | "ready" | "error";

interface HospitalState {
  myHospitals: MyHospital[];
  currentHospitalId: number | null;
  status: HospitalStatus;
  /** 등록 병원 로드 + 현재 병원 보정. 온보딩 게이트가 최초 1회 호출. */
  load: () => Promise<void>;
  /** 현재 병원 전환(앱 전역). */
  setCurrent: (hospitalid: number) => void;
  /** 병원 등록 → 목록 갱신. 첫 등록은 백엔드가 자동 primary 처리. */
  add: (hospitalid: number) => Promise<void>;
  /** 병원 해제 → 목록 갱신. */
  remove: (hospitalid: number) => Promise<void>;
  /** 기본 병원 설정 → 목록 갱신. */
  setPrimary: (hospitalid: number) => Promise<void>;
  /** 로그인/로그아웃 시 호출 — 이전 계정 데이터를 비우고 idle로 되돌려 재로드되게 한다. */
  reset: () => void;
}

const readStoredCurrent = (): number | null => {
  if (typeof window === "undefined") return null;
  const value = Number(window.localStorage.getItem(CURRENT_KEY));
  return value > 0 ? value : null;
};

const writeStoredCurrent = (hospitalid: number | null) => {
  if (typeof window === "undefined") return;
  if (hospitalid == null) {
    window.localStorage.removeItem(CURRENT_KEY);
  } else {
    window.localStorage.setItem(CURRENT_KEY, String(hospitalid));
  }
};

// 현재 병원 결정: 이전 선택이 목록에 남아 있으면 유지 → 없으면 primary → 그것도 없으면 첫 번째.
const pickCurrent = (list: MyHospital[], prev: number | null): number | null => {
  if (list.length === 0) return null;
  if (prev != null && list.some((h) => h.hospitalid === prev)) return prev;
  const primary = list.find((h) => h.is_primary);
  return primary ? primary.hospitalid : list[0].hospitalid;
};

export const useHospitalStore = create<HospitalState>((set, get) => ({
  myHospitals: [],
  currentHospitalId: readStoredCurrent(),
  status: "idle",

  load: async () => {
    set({ status: "loading" });
    try {
      const list = await getMyHospitals();
      const current = pickCurrent(list, get().currentHospitalId);
      writeStoredCurrent(current);
      set({ myHospitals: list, currentHospitalId: current, status: "ready" });
    } catch {
      // 백엔드 미가동/오류는 error 상태로만 둔다(mock 폴백 금지). 게이트는 통과시킨다.
      set({ status: "error" });
    }
  },

  setCurrent: (hospitalid) => {
    writeStoredCurrent(hospitalid);
    set({ currentHospitalId: hospitalid });
  },

  add: async (hospitalid) => {
    await addMyHospital(hospitalid);
    await get().load();
  },

  remove: async (hospitalid) => {
    await removeMyHospital(hospitalid);
    await get().load();
  },

  setPrimary: async (hospitalid) => {
    await setPrimaryHospital(hospitalid);
    // 기본 병원으로 지정하면 앱 전역 '현재 병원'도 그 병원으로 전환(홈/예약/챗봇/병원탭 연동).
    get().setCurrent(hospitalid);
    await get().load();
  },

  reset: () => {
    writeStoredCurrent(null);
    set({ myHospitals: [], currentHospitalId: null, status: "idle" });
  },
}));
