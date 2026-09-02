import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Entry pages mirror the FastAPI routes that serve them:
//   /       → index.html   (configurator)
//   /video  → video.html   (video studio)
//   /help   → help.html    (parameter docs)
//   /admin  → admin.html   (local catalogue administration)
// In dev, API + /catalog.js are proxied to the FastAPI server — start it
// first (./app-v2/run.sh), then `npm run dev` here.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        video: resolve(import.meta.dirname, "video.html"),
        help: resolve(import.meta.dirname, "help.html"),
        editorial: resolve(import.meta.dirname, "editorial.html"),
        experiments: resolve(import.meta.dirname, "experiments.html"),
        admin: resolve(import.meta.dirname, "admin.html"),
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:7861",
      "/catalog.js": "http://localhost:7861",
      "/healthz": "http://localhost:7861",
    },
  },
});
