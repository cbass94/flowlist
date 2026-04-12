import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
        proxy: {
            // Forward /api/* to FastAPI backend in dev
            "/api": {
                target: "http://backend:8000",
                changeOrigin: true,
            },
        },
    },
});
