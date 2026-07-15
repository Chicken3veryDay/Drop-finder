const unsafeAbsolutePattern = /^(?:[a-z]+:)?\/\//i;

export const publicationPath = (path: string): string => {
  const normalized = path.trim().replace(/^\.\//, "").replace(/^\/+/, "");
  if (!normalized || unsafeAbsolutePattern.test(path) || path.startsWith("/")) {
    throw new Error(`Publication assets must use a non-empty relative path: ${path}`);
  }
  if (normalized.split("/").includes("..")) {
    throw new Error(`Publication assets may not escape the publication root: ${path}`);
  }
  return `./${normalized}`;
};

export const PUBLICATION_ASSETS = {
  manifest: publicationPath("manifest.webmanifest"),
  icon: publicationPath("icon.svg"),
  serviceWorker: publicationPath("sw.js"),
  catalog: publicationPath("data/catalog.json"),
  status: publicationPath("data/status.json"),
  runtime: publicationPath("data/runtime.json"),
} as const;
