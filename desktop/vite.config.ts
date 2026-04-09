import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "../static/desktop",
    emptyDirBeforeWrite: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:6969",
      "/ws": { target: "ws://localhost:6969", ws: true },
    },
  },
});
