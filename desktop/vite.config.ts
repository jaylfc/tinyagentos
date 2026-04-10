import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/desktop/",
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "../static/desktop",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        chat: path.resolve(__dirname, "chat.html"),
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:6969",
      "/ws": { target: "ws://localhost:6969", ws: true },
    },
  },
});
