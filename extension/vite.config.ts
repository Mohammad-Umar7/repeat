import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Builds only the side panel (React). Service worker and content scripts are
// bundled as IIFEs by build.mjs because MV3 content scripts cannot be ES modules.
export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname, "src/sidepanel"),
  publicDir: resolve(__dirname, "public"),
  resolve: { alias: { "@shared": resolve(__dirname, "src/shared") } },
  build: {
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: false,
    sourcemap: false,
    target: "chrome120",
    rollupOptions: {
      input: resolve(__dirname, "src/sidepanel/index.html"),
      output: {
        entryFileNames: "sidepanel/[name].js",
        chunkFileNames: "sidepanel/[name]-[hash].js",
        assetFileNames: "sidepanel/[name][extname]",
      },
    },
  },
});
