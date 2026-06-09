/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GUARDIAN_URL?: string;
  readonly VITE_VET_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
