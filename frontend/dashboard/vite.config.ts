import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // In dev, proxy directly to the replay dashboard (8775).
      // In production the gateway (8888) handles this routing.
      "/api/replay": "http://127.0.0.1:8775",
      "/api": "http://127.0.0.1:8888",
      "/collision_meshes": "http://127.0.0.1:8775"
    }
  },
  build: {
    outDir: "dist",
    sourcemap: true
  }
});
