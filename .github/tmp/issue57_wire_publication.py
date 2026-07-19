from pathlib import Path

path = Path('.github/workflows/dropfinder-cloud.yml')
text = path.read_text(encoding='utf-8')


def replace(old: str, new: str, expected: int = 1) -> None:
    global text
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'expected {expected} occurrences, found {count}: {old[:80]!r}')
    text = text.replace(old, new)


replace(
    '      - "scripts/catalog_v4/**"\n',
    '      - "scripts/catalog_v4/**"\n'
    '      - "scripts/vendor_adapters/**"\n'
    '      - "data/vendor_profiles.json"\n'
    '      - "data/vendor_expansion.json"\n',
    2,
)
replace(
    '      - "tests/test_publication_release.py"\n',
    '      - "tests/test_publication_release.py"\n'
    '      - "tests/test_vendor_document_publication.py"\n',
    2,
)
replace(
    '            scripts/publication_release.py web/scripts/publication_gate.py\n',
    '            scripts/publication_release.py web/scripts/publication_gate.py\n'
    '          python -m compileall -q scripts/vendor_adapters\n',
)
replace(
    '            tests.test_publication_release \\\n'
    '            tests.test_dropfinder_cloud_workflow_permissions\n',
    '            tests.test_publication_release \\\n'
    '            tests.test_vendor_document_publication \\\n'
    '            tests.test_dropfinder_cloud_workflow_permissions\n',
)
replace(
    '          python scripts/autonomous_merge.py \\\n'
    '            --input scan-results --output /tmp/dropfinder-generated-data \\\n'
    '            --min-active 5 --min-products 25\n'
    '          python -m scripts.catalog_v4 \\\n',
    '          python scripts/autonomous_merge.py \\\n'
    '            --input scan-results --output /tmp/dropfinder-generated-data \\\n'
    '            --min-active 5 --min-products 25\n'
    '          python -m scripts.vendor_adapters.publication generate \\\n'
    '            --catalog /tmp/dropfinder-generated-data/catalog.json \\\n'
    '            --profiles data/vendor_profiles.json \\\n'
    '            --output /tmp/dropfinder-generated-data/vendor-document-artifact.json \\\n'
    '            --timeout 8 \\\n'
    '            --max-product-pages-per-vendor 4\n'
    '          python -m scripts.vendor_adapters.publication verify \\\n'
    '            --artifact /tmp/dropfinder-generated-data/vendor-document-artifact.json \\\n'
    '            --catalog /tmp/dropfinder-generated-data/catalog.json \\\n'
    '            --profiles data/vendor_profiles.json\n'
    '          python -m scripts.catalog_v4 \\\n',
)
replace(
    '            --output /tmp/dropfinder-generated-data \\\n'
    '            --detail-shards 16 \\\n',
    '            --output /tmp/dropfinder-generated-data \\\n'
    '            --vendor-profiles data/vendor_profiles.json \\\n'
    '            --vendor-expansion data/vendor_expansion.json \\\n'
    '            --documents /tmp/dropfinder-generated-data/vendor-document-artifact.json \\\n'
    '            --detail-shards 16 \\\n',
)
replace(
    '          python web/scripts/publication_gate.py verify-published --root /tmp/dropfinder-candidate\n'
    '          python -m scripts.catalog_v4 \\\n',
    '          python web/scripts/publication_gate.py verify-published --root /tmp/dropfinder-candidate\n'
    '          python -m scripts.vendor_adapters.publication verify \\\n'
    '            --artifact /tmp/dropfinder-candidate/data/vendor-document-artifact.json \\\n'
    '            --catalog /tmp/dropfinder-candidate/data/catalog.json \\\n'
    '            --profiles data/vendor_profiles.json\n'
    '          python -m scripts.catalog_v4 \\\n',
)
replace(
    '            /tmp/pages-verification.json\n'
    '            deployment/release.json\n',
    '            /tmp/pages-verification.json\n'
    '            /tmp/dropfinder-pages/data/vendor-document-artifact.json\n'
    '            deployment/release.json\n',
)
path.write_text(text, encoding='utf-8')
