// Bundles the MV3 service worker and content scripts as self-contained IIFEs.
import { build, context } from "esbuild";
import { mkdirSync, cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const watch = process.argv.includes("--watch");
const outdir = resolve("dist");
mkdirSync(outdir, { recursive: true });

const common = {
  bundle: true,
  format: "iife",
  target: "chrome120",
  sourcemap: false,
  minify: false,
  legalComments: "none",
  logLevel: "info",
  alias: { "@shared": resolve("src/shared") },
  define: {
    "process.env.NODE_ENV": '"production"',
    __REPEAT_PORT__: JSON.stringify(process.env.REPEAT_PORT || "8765"),
  },
};

const entries = [
  { entryPoints: ["src/background/index.ts"], outfile: "dist/background.js" },
  { entryPoints: ["src/content/recorder.ts"], outfile: "dist/content/recorder.js" },
  { entryPoints: ["src/content/ghost/index.ts"], outfile: "dist/content/ghost.js" },
];

// public/ is also copied by vite; copying here keeps `node build.mjs` alone usable.
if (existsSync("public")) cpSync("public", outdir, { recursive: true });

if (watch) {
  for (const e of entries) (await context({ ...common, ...e })).watch();
  console.log("[repeat] esbuild watching…");
} else {
  await Promise.all(entries.map((e) => build({ ...common, ...e })));
  console.log("[repeat] scripts bundled");
}
