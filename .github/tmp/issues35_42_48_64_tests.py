from pathlib import Path


Path("web/test/document-viewer-controls.test.mjs").write_text(r'''import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

function readyViewer(parentWidth) {
  const viewer = new DocumentViewerCapability({ minScale: 0.5, maxScale: 3, initialScale: 1 });
  const pdfPage = {
    getViewport: ({ scale }) => ({ width: 400 * scale, height: 600 * scale }),
    render: () => ({ promise: Promise.resolve(), cancel() {} }),
    cleanup() {},
  };
  const session = {
    id: 'session',
    controller: new AbortController(),
    loadingTask: null,
    pdf: { getPage: async () => pdfPage },
    renderTask: null,
    renderRevision: 0,
    renderSequence: Promise.resolve(),
    objectUrl: null,
  };
  viewer.session = session;
  viewer.setState({
    status: 'ready', type: 'pdf', documentRef: { url: 'https://example.test/report.pdf' }, context: {},
    page: 1, pages: 1, scale: 1, renderedScale: 1, fitWidth: true,
    displayUrl: null, error: null, sessionId: session.id,
  });
  const canvas = {
    parentElement: { clientWidth: parentWidth },
    style: {},
    getContext: () => ({}),
  };
  return { viewer, canvas };
}

test('manual zoom starts from the rendered fit-width scale', async () => {
  const wide = readyViewer(1000);
  const wideRender = await wide.viewer.renderPage(wide.canvas);
  assert.equal(wideRender.scale, 2.5);
  assert.equal(wide.viewer.snapshot().renderedScale, 2.5);
  wide.viewer.zoomIn();
  assert.equal(wide.viewer.snapshot().scale, 2.75);
  assert.equal(wide.viewer.snapshot().fitWidth, false);

  const narrow = readyViewer(200);
  const narrowRender = await narrow.viewer.renderPage(narrow.canvas);
  assert.equal(narrowRender.scale, 0.5);
  narrow.viewer.zoomOut();
  assert.equal(narrow.viewer.snapshot().scale, 0.5);
  assert.equal(narrow.viewer.snapshot().fitWidth, false);
});

test('reset zoom restores the configured manual scale', async () => {
  const { viewer, canvas } = readyViewer(800);
  await viewer.renderPage(canvas);
  viewer.zoomIn();
  assert.notEqual(viewer.snapshot().scale, 1);
  viewer.resetZoom();
  assert.equal(viewer.snapshot().scale, 1);
  assert.equal(viewer.snapshot().renderedScale, 1);
  assert.equal(viewer.snapshot().fitWidth, false);
});
''', encoding="utf-8")

Path("web/src/features/integration/document-overlay-controls.test.tsx").write_text(r'''import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      state = { ...state, status: "closed", type: null, documentRef: null, sessionId: null } as typeof state;
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
    function Harness() {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button type="button">Invoker</button>
          {open ? (
            <DocumentOverlay
              viewer={viewer as never}
              request={{ productId: "p1", variantId: "v1", document: documentRef, invokingElement: screen.queryByRole("button", { name: "Invoker" }) as HTMLElement }}
              onClosed={() => setOpen(false)}
            />
          ) : null}
        </>
      );
    }
    render(<Harness />);
    const invoker = screen.getByRole("button", { name: "Invoker" });
    const dialog = screen.getByRole("dialog", { name: "Lab report" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Lab report" })).toBeNull());
    expect(viewer.close).toHaveBeenCalledTimes(1);
    expect(viewer.close).toHaveBeenCalledWith({ restoreFocus: false });
    expect(document.activeElement).toBe(invoker);
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
''', encoding="utf-8")
