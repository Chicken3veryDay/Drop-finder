import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentOverlay } from "./register-marketplace-props";
import type { MarketplaceDocument } from "../marketplace/marketplace-core";

const documentRef: MarketplaceDocument = {
  id: "report",
  kind: "coa",
  url: "https://example.test/report.pdf",
  format: "pdf",
  title: "Lab report",
  mimeType: "application/pdf",
};

let resizeCallback: ResizeObserverCallback | null = null;
const originalResizeObserver = globalThis.ResizeObserver;
const originalRect = HTMLElement.prototype.getBoundingClientRect;

beforeEach(() => {
  resizeCallback = null;
  globalThis.ResizeObserver = class {
    constructor(callback: ResizeObserverCallback) { resizeCallback = callback; }
    observe() {}
    disconnect() {}
    unobserve() {}
  } as unknown as typeof ResizeObserver;
  HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
    x: 0, y: 0, width: 320, height: 480, top: 0, right: 320, bottom: 480, left: 0,
    toJSON: () => ({}),
  }));
});

afterEach(() => {
  globalThis.ResizeObserver = originalResizeObserver;
  HTMLElement.prototype.getBoundingClientRect = originalRect;
});

function fakeViewer() {
  let state = {
    status: "ready", type: "pdf", documentRef, page: 1, pages: 2,
    scale: 1, renderedScale: 1, fitWidth: true, displayUrl: null,
    error: null, sessionId: "session",
  };
  const listeners = new Set<(value: typeof state) => void>();
  return {
    open: vi.fn(),
    close: vi.fn(async () => {
      state = { ...state, status: "closed", type: null, documentRef: null, sessionId: null } as unknown as typeof state;
      for (const listener of listeners) listener(state);
    }),
    subscribe: vi.fn((listener: (value: typeof state) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }),
    snapshot: vi.fn(() => state),
    renderPage: vi.fn(async () => ({ page: 1, scale: 1, width: 320, height: 480 })),
    goToPage: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    resetZoom: vi.fn(),
    setFitWidth: vi.fn(),
    handleKeyDown: vi.fn(() => false),
  };
}

describe("DocumentOverlay controls and ownership", () => {
  it("removes the modal once on Escape and restores focus after cleanup", async () => {
    const viewer = fakeViewer();
    const invoker = document.createElement("button");
    invoker.type = "button";
    invoker.textContent = "Invoker";
    document.body.append(invoker);
    function Harness() {
      const [open, setOpen] = useState(true);
      return open ? (
        <DocumentOverlay
          viewer={viewer as never}
          request={{ productId: "p1", variantId: "v1", document: documentRef, invokingElement: invoker }}
          onClosed={() => setOpen(false)}
        />
      ) : null;
    }
    render(<Harness />);
    const dialog = screen.getByRole("dialog", { name: "Lab report" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Lab report" })).toBeNull());
    expect(viewer.close).toHaveBeenCalledTimes(1);
    expect(viewer.close).toHaveBeenCalledWith({ restoreFocus: false });
    await waitFor(() => expect(document.activeElement).toBe(invoker));
    invoker.remove();
  });

  it("exposes reset zoom and rerenders fit-width PDFs after stage resize", async () => {
    const viewer = fakeViewer();
    const invoker = document.createElement("button");
    document.body.append(invoker);
    render(
      <DocumentOverlay
        viewer={viewer as never}
        request={{ productId: "p1", variantId: "v1", document: documentRef, invokingElement: invoker }}
        onClosed={() => undefined}
      />,
    );
    await waitFor(() => expect(viewer.renderPage).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Reset zoom" }));
    expect(viewer.resetZoom).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Fit width" })).toBeVisible();

    resizeCallback?.([{ contentRect: { width: 640 } } as ResizeObserverEntry], {} as ResizeObserver);
    await waitFor(() => expect(viewer.renderPage).toHaveBeenCalledTimes(2));
    invoker.remove();
  });
});
