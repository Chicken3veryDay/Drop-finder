import { describe, expect, it, vi } from "vitest";
import type { DocumentViewerRequest, MarketplaceDocument } from "../marketplace/marketplace-core";
import { openMarketplaceDocument } from "./register-marketplace-props";

const document: MarketplaceDocument = {
  id: "document-p1-v1",
  kind: "coa",
  url: "https://example.test/report.pdf",
  format: "pdf",
  mimeType: "application/pdf",
  title: "Report",
};

const request: DocumentViewerRequest = {
  productId: "p1",
  variantId: "v1",
  document,
  invokingElement: null,
};

function state(status: string, type: string | null) {
  return {
    status,
    type,
    documentRef: document,
    page: 1,
    pages: type === "pdf" ? 1 : null,
    scale: 1,
    renderedScale: 1,
    fitWidth: true,
    displayUrl: null,
    error: status === "error" ? { message: "failed" } : null,
    sessionId: "session-1",
  };
}

function viewer(snapshot = state("ready", "pdf")) {
  return {
    open: vi.fn(async () => undefined),
    close: vi.fn(async () => undefined),
    subscribe: vi.fn(() => () => undefined),
    snapshot: vi.fn(() => snapshot),
    renderPage: vi.fn(async () => undefined),
    goToPage: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    resetZoom: vi.fn(),
    setFitWidth: vi.fn(),
    handleKeyDown: vi.fn(() => false),
  };
}

function pwa(cacheOpenedDocument = vi.fn(async () => true)) {
  return {
    register: vi.fn(async () => null),
    cacheOpenedDocument,
  };
}

describe("integrated opened-document caching", () => {
  it("requests one background cache write after a supported document is ready", async () => {
    const documentViewer = viewer();
    const cacheOpenedDocument = vi.fn(async () => true);
    const coordinator = pwa(cacheOpenedDocument);

    await openMarketplaceDocument(documentViewer, coordinator, request);
    await Promise.resolve();

    expect(documentViewer.open).toHaveBeenCalledTimes(1);
    expect(cacheOpenedDocument).toHaveBeenCalledTimes(1);
    expect(cacheOpenedDocument).toHaveBeenCalledWith(document);
  });

  it("does not cache failed, unsupported, or external-only opens", async () => {
    for (const snapshot of [
      state("error", "pdf"),
      state("unsupported", "unsupported"),
      state("external-only", "html"),
    ]) {
      const cacheOpenedDocument = vi.fn(async () => true);
      await openMarketplaceDocument(viewer(snapshot), pwa(cacheOpenedDocument), request);
      await Promise.resolve();
      expect(cacheOpenedDocument).not.toHaveBeenCalled();
    }
  });

  it("does not block or reject the successful open when background caching fails", async () => {
    let rejectCache: (error: Error) => void = () => undefined;
    const pending = new Promise<boolean>((_resolve, reject) => { rejectCache = reject; });
    const cacheOpenedDocument = vi.fn(() => pending);

    await expect(openMarketplaceDocument(viewer(), pwa(cacheOpenedDocument), request)).resolves.toBeUndefined();
    await Promise.resolve();
    expect(cacheOpenedDocument).toHaveBeenCalledTimes(1);

    rejectCache(new Error("cache unavailable"));
    await Promise.resolve();
    await Promise.resolve();
  });
});
