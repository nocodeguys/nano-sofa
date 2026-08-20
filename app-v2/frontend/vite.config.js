import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Three entry pages, mirroring the FastAPI routes that serve them:
//   /       → index.html   (configurator)
//   /video  → video.html   (video studio)
//   /help   → help.html    (parameter docs)
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
