import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";
export default defineConfig({
    plugins: [react()],
    appType: "spa",
    resolve: {
        alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
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
