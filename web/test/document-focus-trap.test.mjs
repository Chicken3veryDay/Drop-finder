import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

function createNode(name) {
  return {
    name,
    hidden: false,
    getAttribute() { return null; },
    focus() { globalThis.document.activeElement = this; },
  };
}

function createTabEvent({ shiftKey = false } = {}) {
  return {
    key: 'Tab',
    shiftKey,
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
  };
}

function withFocusFixture(activeName, run) {
  const previousDocument = globalThis.document;
  const root = createNode('root');
  const first = createNode('first');
  const middle = createNode('middle');
  const last = createNode('last');
  const outside = createNode('outside');
  const nodes = { root, first, middle, last, outside };
  root.querySelectorAll = () => [first, middle, last];
  globalThis.document = { activeElement: nodes[activeName] };

  try {
    const viewer = new DocumentViewerCapability();
    viewer.setState({ status: 'ready' });
    run({ viewer, root, first, middle, last, outside });
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
}

test('Shift+Tab from the focused overlay root wraps to the final control', () => {
  withFocusFixture('root', ({ viewer, root, last }) => {
    const event = createTabEvent({ shiftKey: true });
    assert.equal(viewer.handleKeyDown(event, root), true);
    assert.equal(event.defaultPrevented, true);
    assert.equal(globalThis.document.activeElement, last);
  });
});

test('Tab from unexpected outside focus is redirected to the first control', () => {
  withFocusFixture('outside', ({ viewer, root, first }) => {
    const event = createTabEvent();
    assert.equal(viewer.handleKeyDown(event, root), true);
    assert.equal(event.defaultPrevented, true);
    assert.equal(globalThis.document.activeElement, first);
  });
});

test('focus wrapping at the first and last controls remains intact', () => {
  withFocusFixture('first', ({ viewer, root, last }) => {
    const backward = createTabEvent({ shiftKey: true });
    assert.equal(viewer.handleKeyDown(backward, root), true);
    assert.equal(backward.defaultPrevented, true);
    assert.equal(globalThis.document.activeElement, last);
  });
  withFocusFixture('last', ({ viewer, root, first }) => {
    const forward = createTabEvent();
    assert.equal(viewer.handleKeyDown(forward, root), true);
    assert.equal(forward.defaultPrevented, true);
    assert.equal(globalThis.document.activeElement, first);
  });
});

test('Tab from an interior control follows normal browser navigation', () => {
  withFocusFixture('middle', ({ viewer, root, middle }) => {
    const event = createTabEvent();
    assert.equal(viewer.handleKeyDown(event, root), false);
    assert.equal(event.defaultPrevented, false);
    assert.equal(globalThis.document.activeElement, middle);
  });
});
