import { describe, expect, it } from "vitest";
import { PUBLICATION_ASSETS, publicationPath } from "./assetPaths";

describe("publication paths", () => {
  it("keeps every static path relative for GitHub Pages and raw.githack subpaths", () => {
    expect(Object.values(PUBLICATION_ASSETS).every((path) => path.startsWith("./"))).toBe(true);
    expect(Object.values(PUBLICATION_ASSETS).some((path) => path.startsWith("/"))).toBe(false);
  });

  it("rejects absolute URLs, root paths, and traversal", () => {
    expect(() => publicationPath("/data/catalog.json")).toThrow();
    expect(() => publicationPath("https://example.com/data.json")).toThrow();
    expect(() => publicationPath("../catalog.json")).toThrow();
  });
});
