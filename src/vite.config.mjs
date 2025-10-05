import tailwindcss from "@tailwindcss/vite";

import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  base: "/static/",
  resolve: {
    alias: {
      "@": resolve("./static"),
    },
  },
  build: {
    manifest: "manifest.json",
    outDir: resolve("./assets"),
    assetsDir: "django-assets",
    rollupOptions: {
      input: {
        mainJs: resolve("./static/js/main.js"),
      },
    },
  },
  plugins: [tailwindcss()],
});
