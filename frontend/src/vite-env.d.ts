/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin for production builds, e.g. https://market-api.onrender.com */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
