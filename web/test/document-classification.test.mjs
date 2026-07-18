import assert from 'node:assert/strict';
import test from 'node:test';

import { classifyDocument } from '../src/platform/documents/document-viewer-capability.js';

test('document classification preserves supported URL and MIME boundaries', () => {
  const cases = [
    {
      name: 'relative PDF path with query string',
      documentRef: { url: './reports/lab.pdf?download=1' },
      expected: 'pdf',
    },
    {
      name: 'parent-relative image path with fragment',
      documentRef: { url: '../images/preview.webp#main' },
      expected: 'image',
    },
    {
      name: 'extensionless HTTPS PDF with declared MIME type',
      documentRef: { url: 'https://cdn.example.test/document/123', mimeType: 'application/pdf' },
      expected: 'pdf',
    },
    {
      name: 'extensionless HTTPS image with declared MIME type',
      documentRef: { url: 'https://cdn.example.test/image/123', mimeType: 'image/png' },
      expected: 'image',
    },
    {
      name: 'data URL remains unsupported despite a declared MIME type',
      documentRef: { url: 'data:application/pdf;base64,AA==', mimeType: 'application/pdf' },
      expected: 'unsupported',
    },
    {
      name: 'file URL remains unsupported despite a declared MIME type',
      documentRef: { url: 'file:///tmp/report.pdf', mimeType: 'application/pdf' },
      expected: 'unsupported',
    },
  ];

  for (const { name, documentRef, expected } of cases) {
    assert.equal(classifyDocument(documentRef), expected, name);
  }
});
