import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { defineConfig } from "vite";

// Python in the Output panel runs on Pyodide (Python compiled to WebAssembly) inside the
// sandboxed preview frame. The app fetches these files and hands them to the frame
// (src/preview.js). Only these five files are served from the package.
const require = createRequire(import.meta.url);
const PYODIDE_DIR = dirname(require.resolve("pyodide/package.json"));
const PYODIDE_FILES = {
  "pyodide.mjs": "text/javascript",
  "pyodide.asm.mjs": "text/javascript",
  "pyodide.asm.wasm": "application/wasm",
  "python_stdlib.zip": "application/zip",
  "pyodide-lock.json": "application/json",
};

function pyodideAssets() {
  return {
    name: "pyodide-assets",
    configureServer(server) {
      server.middlewares.use("/pyodide/", (request, response, next) => {
        const name = decodeURIComponent((request.url || "").split("?")[0].replace(/^\//, ""));
        const type = PYODIDE_FILES[name];
        if (!type) { next(); return; }
        response.setHeader("Content-Type", type);
        response.setHeader("Cache-Control", "public, max-age=86400");
        response.end(readFileSync(join(PYODIDE_DIR, name)));
      });
    },
    generateBundle() {
      for (const name of Object.keys(PYODIDE_FILES)) {
        this.emitFile({ type: "asset", fileName: `pyodide/${name}`, source: readFileSync(join(PYODIDE_DIR, name)) });
      }
    },
  };
}

export default defineConfig({
  plugins: [pyodideAssets()],
});
