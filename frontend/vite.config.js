import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: "all",
    watch: {
      usePolling: true,   // required for Docker on Windows (no inotify across bind mounts)
      interval: 500,       // ms between polls
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
