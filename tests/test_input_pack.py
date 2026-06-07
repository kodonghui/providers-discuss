from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from providers_discuss.input_pack import scan_source_dirs


class InputPackTests(unittest.TestCase):
    def test_scan_source_dirs_skips_generated_state_dirs(self) -> None:
        # Given: a source tree contains real notes plus generated runner state.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.md").write_text("# Keep\n\nreal input\n", encoding="utf-8")
            (root / ".omo").mkdir()
            (root / ".omo" / "ledger.jsonl").write_text('{"generated": true}\n', encoding="utf-8")
            (root / "input-pack").mkdir()
            (root / "input-pack" / "input-pack.md").write_text("generated pack\n", encoding="utf-8")

            # When: the input pack scanner walks the source directory.
            rows = scan_source_dirs(source_dirs=[root], max_file_bytes=64 * 1024, excerpt_lines=4)

            # Then: generated state is not included as provider input.
            included_paths = [row["path"] for row in rows if row["included"]]
            self.assertEqual(included_paths, ["keep.md"])

    def test_scan_source_dirs_keeps_text_when_utf8_prefix_ends_mid_character(self) -> None:
        # Given: a UTF-8 text file whose sniff prefix ends inside a multibyte char.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = root / "split-prefix.txt"
            text_path.write_bytes((b"a" * 4095) + "é\n".encode("utf-8"))

            # When: the scanner classifies the file.
            rows = scan_source_dirs(source_dirs=[root], max_file_bytes=64 * 1024, excerpt_lines=1)

            # Then: incomplete UTF-8 at the sniff boundary is treated as text, not binary.
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["included"])
            self.assertEqual(rows[0]["path"], "split-prefix.txt")


if __name__ == "__main__":
    unittest.main()
