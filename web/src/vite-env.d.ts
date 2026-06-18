/// <reference types="vite/client" />

// Injected at build/dev time by Vite `define` from package.json's version.
declare const __APP_VERSION__: string

interface ImportMetaEnv {
  readonly VITE_ARGUS_API?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
