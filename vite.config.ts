import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const isolationHeaders = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

const isServerBuild = process.argv.includes("server");

export default defineConfig({
  base: '/operators/',
  publicDir: isServerBuild ? false : "public",
  plugins: [vue()],
  server: {
    headers: isolationHeaders,
  },
  preview: {
    headers: isolationHeaders,
  },
  worker: {
    format: "es",
  },
  build: {
    outDir: 'ARKExcelsMaker'
  }
});
