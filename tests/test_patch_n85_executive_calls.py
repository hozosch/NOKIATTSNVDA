from __future__ import annotations

import unittest

from tools.patch_n85_executive_calls import (
    END,
    INCLUDE_ANCHOR,
    MARKER,
    REPLACEMENT,
    START,
    TLS_DECLARATIONS,
    TLS_FREE,
    TLS_FREE_PATCH,
    TLS_GET,
    TLS_GET_PATCH,
    TLS_SET,
    TLS_SET_PATCH,
    patch_source,
)


class PatchN85ExecutiveCallsTest(unittest.TestCase):
    def test_replaces_svc_veneer(self) -> None:
        source = (
            f"prefix\n{INCLUDE_ANCHOR}{START}\nold body\n{END}\n"
            f"{TLS_GET}\n{TLS_SET}\n{TLS_FREE}\ntail\n"
        )
        patched = patch_source(source)
        self.assertIn(REPLACEMENT, patched)
        self.assertIn(MARKER, patched)
        self.assertIn(TLS_DECLARATIONS, patched)
        self.assertIn(TLS_GET_PATCH, patched)
        self.assertIn(TLS_SET_PATCH, patched)
        self.assertIn(TLS_FREE_PATCH, patched)
        self.assertNotIn("old body", patched)
        self.assertEqual(patched.count(END), 1)

    def test_is_idempotent(self) -> None:
        source = (
            f"{INCLUDE_ANCHOR}{TLS_DECLARATIONS}{REPLACEMENT}{END}\n"
            f"{TLS_GET_PATCH}\n{TLS_SET_PATCH}\n{TLS_FREE_PATCH}\n"
        )
        self.assertEqual(patch_source(source), source)

    def test_rejects_missing_labels(self) -> None:
        with self.assertRaisesRegex(ValueError, "labels not found"):
            patch_source("unrelated")

    def test_rejects_ambiguous_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "start label is ambiguous"):
            patch_source(f"{START}\none\n{START}\ntwo\n{END}\n")


if __name__ == "__main__":
    unittest.main()
