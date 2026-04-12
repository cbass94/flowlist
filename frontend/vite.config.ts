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
    // Allow all hosts so requests proxied through Caddy (which uses the
    // original Host header) are not rejected by Vite's host check.
    allowedHosts: true,
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
