from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "patch_6650_exclusive_store.py"
SPEC = importlib.util.spec_from_file_location("patch_6650_exclusive_store", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class Patch6650ExclusiveStoreTests(unittest.TestCase):
    def test_replaces_only_broken_strex_block(self) -> None:
        original = "before\n" + PATCH.START + "\nbroken\n" + PATCH.END + "\nafter\n"
        result = PATCH.patch_source(original)
        self.assertEqual(result, "before\n" + PATCH.REPLACEMENT + PATCH.END + "\nafter\n")
        self.assertIn("nokia_mem_store", result)
        self.assertIn("Native 6650 single-threaded store-exclusive", result)
        self.assertIn("reg_lr=0u", result)
        self.assertNotIn("broken", result)

    def test_rejects_missing_labels(self) -> None:
        with self.assertRaisesRegex(ValueError, "labels not found"):
            PATCH.patch_source("no generated labels here\n")

    def test_rejects_ambiguous_labels(self) -> None:
        source = PATCH.START + "\na\n" + PATCH.END + "\n" + PATCH.START + "\nb\n"
        with self.assertRaisesRegex(ValueError, "start label is ambiguous"):
            PATCH.patch_source(source)


if __name__ == "__main__":
    unittest.main()
