from __future__ import annotations

import unittest

from scripts.catalog_v4.document_urls import canonical_document_url
from scripts.catalog_v4.documents import normalize_documents


class DocumentNormalizationTests(unittest.TestCase):
    def test_query_addressed_documents_preserve_distinct_identity(self) -> None:
        documents = normalize_documents(
            [
                {
                    "kind": "coa",
                    "url": "https://lab.example/download?id=coa-123&export=download",
                },
                {
                    "kind": "coa",
                    "url": "https://lab.example/download?id=coa-456&export=download",
                },
            ],
            product_id="product-1",
        )

        self.assertEqual(len(documents), 2)
        self.assertEqual(
            {document["public_url"] for document in documents},
            {
                "https://lab.example/download?export=download&id=coa-123",
                "https://lab.example/download?export=download&id=coa-456",
            },
        )
        self.assertEqual(len({document["document_id"] for document in documents}), 2)

    def test_tracking_parameters_do_not_create_duplicate_documents(self) -> None:
        documents = normalize_documents(
            [
                {
                    "kind": "coa",
                    "url": "https://lab.example/download?id=coa-123&utm_source=newsletter",
                },
                {
                    "kind": "coa",
                    "url": "https://lab.example/download?fbclid=tracking&id=coa-123",
                },
            ],
            product_id="product-1",
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["public_url"], "https://lab.example/download?id=coa-123")

    def test_expiring_or_signed_document_urls_fail_closed(self) -> None:
        signed_urls = (
            "https://lab.example/coa.pdf?X-Amz-Signature=secret&X-Amz-Expires=300",
            "https://lab.example/coa.pdf?Expires=1700000000&Signature=secret",
            "https://lab.example/coa.pdf?token=secret",
        )

        for url in signed_urls:
            with self.subTest(url=url):
                self.assertEqual(canonical_document_url(url), "")
                self.assertEqual(
                    normalize_documents([{"kind": "coa", "url": url}], product_id="product-1"),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
