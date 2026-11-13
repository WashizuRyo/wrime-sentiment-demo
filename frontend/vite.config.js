import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    strictPort: true,
    proxy: {
      "/predict": {
        target: process.env.WRIME_LOCAL_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        timeout: 120000,
      },
    },
  },
});
