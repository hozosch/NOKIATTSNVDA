#!/usr/bin/env python3
"""Unit checks for the generated 5320 frontend latency rewrite."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from patch_5320_frontend_latency import (  # noqa: E402
    DISPATCH_ENTRY,
    FILL_LOOP_ENTRY,
    ITERATOR_ENTRY,
    patch_source,
)


class FrontendLatencyPatchTest(unittest.TestCase):
    def setUp(self):
        self.source = "".join(
            (
                "prefix\n",
                ITERATOR_ENTRY,
                "iterator body\n",
                FILL_LOOP_ENTRY,
                "fill body\n",
                DISPATCH_ENTRY,
                "\nsuffix\n",
            )
        )

    def test_all_three_paths_are_installed(self):
        patched = patch_source(self.source)
        self.assertIn("bounded 16-bit Prime iterator", patched)
        self.assertIn("packed Prime segment fill loop", patched)
        self.assertIn("fixed-stride element address", patched)
        self.assertIn("L_830e1934_slow:", patched)
        self.assertIn("L_830dbae8_slow:", patched)
        self.assertEqual(1, patched.count(DISPATCH_ENTRY))

    def test_reapplying_patch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "already installed"):
            patch_source(patch_source(self.source))

    def test_missing_anchor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Prime fill loop"):
            patch_source(self.source.replace(FILL_LOOP_ENTRY, ""))


if __name__ == "__main__":
    unittest.main()
