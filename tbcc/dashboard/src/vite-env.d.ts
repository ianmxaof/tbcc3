/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  /** Default dashboard target when localStorage has no choice: `local` | `island` */
  readonly VITE_DEFAULT_API_TARGET?: "local" | "island";
  /** Island API origin for Vite proxy (default https://api.powercore.app) */
  readonly VITE_ISLAND_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
