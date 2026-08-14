// Regenerates viz/vendor/three-bundle.min.js (committed artifact).
// Run: cd scripts && npm install && node build-vendor.mjs
import { build } from "esbuild";
import { readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const out = join(root, "viz", "vendor", "three-bundle.min.js");
// three's exports map hides package.json from require(); read it directly
const threeVersion = JSON.parse(
  readFileSync(join(root, "scripts", "node_modules", "three", "package.json"), "utf8")
).version;

await build({
  entryPoints: [join(root, "viz", "vendor", "entry.js")],
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2020",
  outfile: out,
  nodePaths: [join(root, "scripts", "node_modules")],
  banner: {
    js: `/* three.js r${threeVersion} + OrbitControls — MIT License, (c) 2010-2026 three.js authors (https://github.com/mrdoob/three.js) */`,
  },
});

const bundle = readFileSync(out, "utf8");
if (bundle.includes("</script")) {
  // an embedded closing tag would terminate the inline <script> in exports
  throw new Error("bundle contains '</script' — cannot be inlined safely");
}
console.log(`built ${out} (${(statSync(out).size / 1024).toFixed(0)} KB, three r${threeVersion})`);
