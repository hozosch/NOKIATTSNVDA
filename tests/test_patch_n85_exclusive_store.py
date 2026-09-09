from __future__ import annotations

import unittest

from tools.patch_n85_exclusive_store import END, REPLACEMENT, START, patch_source


class PatchN85ExclusiveStoreTest(unittest.TestCase):
    def test_replaces_strex_block(self) -> None:
        source = f"prefix\n{START}\nold body\n{END}\ntail\n"
        patched = patch_source(source)
        self.assertIn(REPLACEMENT, patched)
        self.assertNotIn("old body", patched)
        self.assertEqual(patched.count(END), 1)

    def test_rejects_missing_labels(self) -> None:
        with self.assertRaisesRegex(ValueError, "labels not found"):
            patch_source("unrelated")

    def test_rejects_ambiguous_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "start label is ambiguous"):
            patch_source(f"{START}\none\n{START}\ntwo\n{END}\n")


if __name__ == "__main__":
    unittest.main()
