import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Treat as SPA: serve index.html for all non-asset routes (required for
  // client-side routing via react-router-dom to work on direct navigation).
  appType: "spa",
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    // Explicit allowlist — requests arriving via Caddy carry the original
    // Host header (taskflowlist.com), so Vite must accept it.
    allowedHosts: ["localhost", "taskflowlist.com", "www.taskflowlist.com"],
    proxy: {
      // Forward /api/* to FastAPI backend in dev (when running Vite directly,
      // not through Caddy). In Docker, Caddy handles this routing instead.
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
