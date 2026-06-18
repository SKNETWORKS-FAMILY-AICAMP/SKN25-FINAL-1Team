import { create } from "zustand";
import {
  AuthSession,
  clearSession,
  getSavedSession,
  saveSession,
} from "../api/authApi";

interface SetSessionOptions {
  persist?: boolean;
}

export interface AuthState {
  session: AuthSession | null;
  isAuthenticated: boolean;
  setSession: (session: AuthSession, options?: SetSessionOptions) => void;
  updateAccessToken: (accessToken: string) => void;
  clearAuth: () => void;
}

const savedSession = getSavedSession();

export const useAuthStore = create<AuthState>((set) => ({
  session: savedSession,
  isAuthenticated: Boolean(savedSession),
  setSession: (session, options) => {
    if (options?.persist !== false) {
      saveSession(session);
    }

    set({
      session,
      isAuthenticated: true,
    });
  },
  updateAccessToken: (accessToken) => {
    set((state) => {
      if (!state.session) return state;
      const updated = { ...state.session, accessToken };
      saveSession(updated);
      return { session: updated };
    });
  },
  clearAuth: () => {
    clearSession();
    set({
      session: null,
      isAuthenticated: false,
    });
  },
}));
