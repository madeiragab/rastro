import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dentro do Docker o alvo e http://api:8000; fora, o backend local.
const target = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    watch: { usePolling: true },
    proxy: {
      "/api": { target, changeOrigin: true },
      "/health": { target, changeOrigin: true },
    },
  },
});
