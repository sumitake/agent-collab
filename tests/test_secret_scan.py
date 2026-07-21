"""Fail-closed tests for the repository credential scanner."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "secret_scan.py"


def _load():
    spec = importlib.util.spec_from_file_location("agent_collab_secret_scan", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SecretScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scanner = _load()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_inline_allowlist_marker_cannot_hide_a_real_shaped_token(self) -> None:
        token = "ghp_" + "A" * 36
        (self.root / "credential.txt").write_text(
            token + "  # pragma: allowlist secret\n", encoding="utf-8"
        )
        findings, scanned, errors = self.scanner.scan_tree(self.root)
        self.assertEqual(scanned, 1)
        self.assertEqual(errors, [])
        self.assertTrue(any("GitHub token" in item for item in findings), findings)

    def test_non_utf8_files_are_byte_scanned(self) -> None:
        token = ("AIza" + "A" * 35).encode("ascii")
        (self.root / "opaque.bin").write_bytes(b"\xff\x00" + token + b"\x00")
        findings, scanned, errors = self.scanner.scan_tree(self.root)
        self.assertEqual(scanned, 1)
        self.assertEqual(errors, [])
        self.assertTrue(any("Google API key" in item for item in findings), findings)

    def test_symlinked_source_member_fails_scan_incomplete(self) -> None:
        target = self.root / "target.txt"
        target.write_text("safe", encoding="utf-8")
        (self.root / "linked.txt").symlink_to(target)
        findings, _scanned, errors = self.scanner.scan_tree(self.root)
        self.assertEqual(findings, [])
        self.assertTrue(any("not a regular file" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
