from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.multi_product import strict_publication
from scripts.multi_product.strict_json import StrictJsonError, dumps, loads


class StrictJsonTests(unittest.TestCase):
    def test_rejects_non_standard_constants_and_numeric_overflow(self) -> None:
        for token in ("NaN", "Infinity", "-Infinity", "1e400"):
            with self.subTest(token=token):
                with self.assertRaises(StrictJsonError):
                    loads(f'{{"value":{token}}}', source="fixture")

    def test_rejects_nested_non_finite_python_values(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(StrictJsonError):
                    dumps({"nested": [{"value": value}]})


class StrictPublicationTests(unittest.TestCase):
    def _roots(self, directory: str) -> tuple[Path, Path]:
        root = Path(directory)
        input_dir = root / "input"
        output_dir = root / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "shard-0.json").write_text(
            json.dumps({"schema_version": "dropfinder-autonomous-shard-v1"}),
            encoding="utf-8",
        )
        return input_dir, output_dir

    def test_rejects_non_standard_shard_before_running_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_dir, output_dir = self._roots(directory)
            (input_dir / "shard-0.json").write_text(
                '{"schema_version":"dropfinder-autonomous-shard-v1","price":NaN}',
                encoding="utf-8",
            )
            with mock.patch.object(strict_publication.publication, "merge") as merge:
                with self.assertRaises(StrictJsonError):
                    strict_publication.merge(input_dir, output_dir, 1, 1)
                merge.assert_not_called()

    def test_invalid_staged_output_does_not_replace_live_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_dir, output_dir = self._roots(directory)
            before = {}
            for filename in strict_publication.OUTPUT_FILENAMES:
                text = json.dumps({"sentinel": filename}) + "\n"
                (output_dir / filename).write_text(text, encoding="utf-8")
                before[filename] = text

            def invalid_merge(_input: Path, stage: Path, _active: int, _products: int) -> dict:
                stage.mkdir(parents=True, exist_ok=True)
                for filename in strict_publication.OUTPUT_FILENAMES:
                    text = '{"price":NaN}\n' if filename == "catalog.json" else "{}\n"
                    (stage / filename).write_text(text, encoding="utf-8")
                return {"status": "healthy"}

            with mock.patch.object(strict_publication.publication, "merge", side_effect=invalid_merge):
                with self.assertRaises(StrictJsonError):
                    strict_publication.merge(input_dir, output_dir, 1, 1)

            for filename, text in before.items():
                self.assertEqual((output_dir / filename).read_text(encoding="utf-8"), text)

    def test_valid_staged_outputs_replace_the_complete_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_dir, output_dir = self._roots(directory)

            def valid_merge(_input: Path, stage: Path, _active: int, _products: int) -> dict:
                stage.mkdir(parents=True, exist_ok=True)
                for filename in strict_publication.OUTPUT_FILENAMES:
                    payload = {"filename": filename}
                    if filename == "runtime.json":
                        payload["status"] = "healthy"
                    (stage / filename).write_text(json.dumps(payload) + "\n", encoding="utf-8")
                return {"status": "healthy"}

            with mock.patch.object(strict_publication.publication, "merge", side_effect=valid_merge):
                runtime = strict_publication.merge(input_dir, output_dir, 1, 1)

            self.assertEqual(runtime["status"], "healthy")
            for filename in strict_publication.OUTPUT_FILENAMES:
                payload = loads((output_dir / filename).read_text(encoding="utf-8"))
                self.assertEqual(payload["filename"], filename)


if __name__ == "__main__":
    unittest.main()
