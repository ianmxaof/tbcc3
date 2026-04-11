import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Inject internal API key on proxied /api/* so the browser never sees TBCC_INTERNAL_API_KEY. */
function tbccApiProxy(env: Record<string, string>) {
  const internalKey = (env.TBCC_INTERNAL_API_KEY || "").trim();
  return {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    rewrite: (p: string) => p.replace(/^\/api/, ""),
    configure: (proxy: { on: (ev: string, fn: (...args: unknown[]) => void) => void }) => {
      proxy.on("proxyReq", (proxyReq: { setHeader: (k: string, v: string) => void }) => {
        if (internalKey) {
          proxyReq.setHeader("X-TBCC-Internal-Key", internalKey);
        }
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const tbccRoot = path.resolve(__dirname, "..");
  const env = loadEnv(mode, tbccRoot, "");
  const proxyApi = tbccApiProxy(env);

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // Bind IPv4 loopback only. Browsers often resolve "localhost" to IPv6 (::1) first; if nothing listens on ::1, the side panel iframe shows "localhost refused to connect" while 127.0.0.1 works.
      host: "127.0.0.1",
      strictPort: true,
      // TBCC browser extension embeds the dashboard in the side panel (chrome-extension:// iframe).
      // Without frame-ancestors, some browsers block embedding the dev server.
      headers: {
        "Content-Security-Policy": "frame-ancestors *",
      },
      proxy: {
        "/api": proxyApi,
      },
    },
    preview: {
      port: 5173,
      host: "127.0.0.1",
      strictPort: true,
      headers: {
        "Content-Security-Policy": "frame-ancestors *",
      },
      proxy: {
        "/api": proxyApi,
      },
    },
  };
});
