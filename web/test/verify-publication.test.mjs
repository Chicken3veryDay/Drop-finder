import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { verifyPublication } from "../scripts/verify-publication.mjs";

const write = async (root, path, content) => {
  await mkdir(dirname(resolve(root, path)), { recursive: true });
  await writeFile(resolve(root, path), content);
};

const createPublication = async () => {
  const root = await mkdtemp(resolve(tmpdir(), "dropfinder-publication-"));
  await write(root, "index.html", `<!doctype html>
<html><head>
<link rel="icon" href="./icon.svg">
<link rel="manifest" href="./manifest.webmanifest">
<script type="module" src="./assets/app-ABC123.js"></script>
<link rel="stylesheet" href="./assets/index-DEF456.css">
</head><body></body></html>`);
  await write(root, "manifest.webmanifest", JSON.stringify({ start_url: "./", scope: "./" }));
  await write(root, "icon.svg", "<svg></svg>");
  await write(root, "sw.js", "index.html manifest.webmanifest data/catalog.json data/status.json");
  await write(root, "data/catalog.json", "{}");
  await write(root, "data/status.json", "{}");
  await write(root, "data/runtime.json", "{}");
  await write(root, "assets/app-ABC123.js", "export {};");
  await write(root, "assets/index-DEF456.css", "body{}");
  await write(root, "assets/chunk-GHI789.js", "export {};");
  await write(root, "assets/vite-manifest.json", JSON.stringify({
    "index.html": {
      file: "assets/app-ABC123.js",
      isEntry: true,
      css: ["assets/index-DEF456.css"],
      dynamicImports: ["lazy.js"],
    },
    "lazy.js": { file: "assets/chunk-GHI789.js", isDynamicEntry: true },
  }));
  await write(root, "app-shell.json", JSON.stringify({
    schema_version: "dropfinder-app-shell-v1",
    assets: [
      "./",
      "./index.html",
      "./manifest.webmanifest",
      "./icon.svg",
      "./assets/app-ABC123.js",
      "./assets/index-DEF456.css",
      "./assets/chunk-GHI789.js",
    ],
  }));
  return root;
};

const withPublication = (name, run) => test(name, async () => {
  const root = await createPublication();
  try {
    await run(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

withPublication("accepts a coherent publication dependency closure", async (root) => {
  await assert.doesNotReject(verifyPublication(root));
});

withPublication("rejects a missing HTML entry even when unrelated hashed assets remain", async (root) => {
  await unlink(resolve(root, "assets/app-ABC123.js"));
  await assert.rejects(verifyPublication(root), /Missing or empty publication file: assets\/app-ABC123\.js/);
});

withPublication("rejects root-absolute entry references regardless of quote style", async (root) => {
  for (const script of [
    '<script type="module" src="/assets/app-ABC123.js"></script>',
    "<script type='module' src='/assets/app-ABC123.js'></script>",
    '<SCRIPT TYPE=module SRC=/assets/app-ABC123.js></SCRIPT>',
  ]) {
    await write(root, "index.html", `<!doctype html><html><head>
<link rel="icon" href="./icon.svg">
<link rel="manifest" href="./manifest.webmanifest">
${script}
<link rel="stylesheet" href="./assets/index-DEF456.css">
</head></html>`);
    await assert.rejects(verifyPublication(root), /must use a subpath-safe relative URL/);
  }
});

withPublication("rejects encoded traversal outside the publication root", async (root) => {
  await write(root, "index.html", `<!doctype html><html><head>
<link rel="icon" href="./icon.svg">
<link rel="manifest" href="./manifest.webmanifest">
<script type="module" src="./%2e%2e/escape.js"></script>
<link rel="stylesheet" href="./assets/index-DEF456.css">
</head></html>`);
  await assert.rejects(verifyPublication(root), /escapes the publication root/);
});

withPublication("rejects a Vite manifest whose entry CSS disagrees with the HTML", async (root) => {
  await write(root, "assets/other-JKL012.css", "body{color:red}");
  await write(root, "assets/vite-manifest.json", JSON.stringify({
    "index.html": {
      file: "assets/app-ABC123.js",
      isEntry: true,
      css: ["assets/other-JKL012.css"],
    },
  }));
  await assert.rejects(verifyPublication(root), /HTML stylesheets and Vite entry CSS mismatch/);
});

withPublication("rejects an application shell that omits an HTML dependency", async (root) => {
  await write(root, "app-shell.json", JSON.stringify({
    schema_version: "dropfinder-app-shell-v1",
    assets: [
      "./",
      "./index.html",
      "./manifest.webmanifest",
      "./icon.svg",
      "./assets/index-DEF456.css",
      "./assets/chunk-GHI789.js",
    ],
  }));
  await assert.rejects(verifyPublication(root), /omits index dependency: assets\/app-ABC123\.js/);
});
