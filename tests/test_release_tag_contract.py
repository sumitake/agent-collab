"""Signed release-tag message grammar (fail-closed).

The topology gate and intent binding land with the v3 saga implementation; see the
module docstring for why they are deliberately out of scope here.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_tag_contract.py"

GOOD_ASSET = "a" * 64
GOOD_MANIFEST = "b" * 64


def _load():
    spec = importlib.util.spec_from_file_location("release_tag_contract", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TagGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rtc = _load()

    def _message(self, **over) -> str:
        fields = {"tag": "v4.1.0", "asset_name": "agent-collab v4.1.0.plugin",
                  "asset_sha256": GOOD_ASSET, "manifest_sha256": GOOD_MANIFEST}
        fields.update(over)
        tag = fields.pop("tag")
        return self.rtc.format_tag_message(tag, **fields)

    def test_roundtrip_emits_only_what_it_accepts(self) -> None:
        parsed = self.rtc.parse_tag_message(self._message(), tag="v4.1.0")
        self.assertEqual(parsed["asset_sha256"], GOOD_ASSET)
        self.assertEqual(parsed["manifest_sha256"], GOOD_MANIFEST)
        self.assertEqual(parsed["asset_name"], "agent-collab v4.1.0.plugin")
        self.assertEqual(parsed["schema"], self.rtc.SCHEMA)

    def test_title_must_match_the_exact_tag(self) -> None:
        # A message minted for another tag must not validate against this one.
        message = self._message()
        with self.assertRaisesRegex(self.rtc.TagContractError, "title"):
            self.rtc.parse_tag_message(message, tag="v9.9.9")

    def test_missing_required_field_fails_closed(self) -> None:
        for drop in ("schema", "Asset-Name", "Asset-SHA256", "Manifest-SHA256"):
            message = "\n".join(
                line for line in self._message().strip().splitlines()
                if not line.startswith(f"{drop}:")
            ) + "\n"
            with self.subTest(drop=drop):
                with self.assertRaisesRegex(self.rtc.TagContractError, "missing required"):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")

    def test_duplicate_and_unknown_fields_fail_closed(self) -> None:
        dup = self._message().rstrip("\n") + f"\nAsset-SHA256: {GOOD_ASSET}\n"
        with self.assertRaisesRegex(self.rtc.TagContractError, "duplicate"):
            self.rtc.parse_tag_message(dup, tag="v4.1.0")
        unknown = self._message().rstrip("\n") + "\nX-Injected: whatever\n"
        with self.assertRaisesRegex(self.rtc.TagContractError, "unknown"):
            self.rtc.parse_tag_message(unknown, tag="v4.1.0")

    def test_digests_must_be_lowercase_64_hex(self) -> None:
        for bad, why in ((GOOD_ASSET.upper(), "uppercase"), ("a" * 63, "short"),
                         ("a" * 65, "long"), ("z" * 64, "non-hex")):
            message = self._message().replace(f"Asset-SHA256: {GOOD_ASSET}",
                                              f"Asset-SHA256: {bad}")
            with self.subTest(why=why):
                with self.assertRaisesRegex(self.rtc.TagContractError, "64 lowercase hex"):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")

    def test_unsafe_asset_names_and_non_ascii_fail_closed(self) -> None:
        for bad in ("../escape.plugin", "dir/nested.plugin", "back\\slash.plugin"):
            message = self._message().replace("Asset-Name: agent-collab v4.1.0.plugin",
                                              f"Asset-Name: {bad}")
            with self.subTest(bad=bad), self.assertRaises(self.rtc.TagContractError):
                self.rtc.parse_tag_message(message, tag="v4.1.0")
        non_ascii = self._message().replace("agent-collab v4.1.0.plugin", "agent-collab-café.plugin")
        with self.assertRaisesRegex(self.rtc.TagContractError, "ASCII"):
            self.rtc.parse_tag_message(non_ascii, tag="v4.1.0")

    def test_trailing_material_after_the_field_block_fails_closed(self) -> None:
        trailing = self._message().rstrip("\n") + "\n\nPS: extra narrative\n"
        with self.assertRaises(self.rtc.TagContractError):
            self.rtc.parse_tag_message(trailing, tag="v4.1.0")

    def test_wrong_schema_and_bad_tag_shape_fail_closed(self) -> None:
        wrong = self._message().replace(self.rtc.SCHEMA, "attacker-release/9")
        with self.assertRaisesRegex(self.rtc.TagContractError, "unsupported tag schema"):
            self.rtc.parse_tag_message(wrong, tag="v4.1.0")
        with self.assertRaisesRegex(self.rtc.TagContractError, "vMAJOR"):
            self.rtc.format_tag_message("4.1.0", asset_name="a.plugin",
                                        asset_sha256=GOOD_ASSET, manifest_sha256=GOOD_MANIFEST)

if __name__ == "__main__":
    unittest.main()
