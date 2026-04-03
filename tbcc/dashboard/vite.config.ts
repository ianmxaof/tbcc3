import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
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
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    port: 5173,
    host: "127.0.0.1",
    strictPort: true,
    headers: {
      "Content-Security-Policy": "frame-ancestors *",
    },
  },
});
