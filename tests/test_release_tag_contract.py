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
        fields = {"tag": "v4.1.0", "asset_name": "agent-collab-v4.1.0.plugin",
                  "asset_sha256": GOOD_ASSET, "manifest_sha256": GOOD_MANIFEST}
        fields.update(over)
        tag = fields.pop("tag")
        return self.rtc.format_tag_message(tag, **fields)

    def test_roundtrip_emits_only_what_it_accepts(self) -> None:
        parsed = self.rtc.parse_tag_message(self._message(), tag="v4.1.0")
        self.assertEqual(parsed["asset_sha256"], GOOD_ASSET)
        self.assertEqual(parsed["manifest_sha256"], GOOD_MANIFEST)
        self.assertEqual(parsed["asset_name"], "agent-collab-v4.1.0.plugin")
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
            message = self._message().replace("Asset-Name: agent-collab-v4.1.0.plugin",
                                              f"Asset-Name: {bad}")
            with self.subTest(bad=bad), self.assertRaises(self.rtc.TagContractError):
                self.rtc.parse_tag_message(message, tag="v4.1.0")
        non_ascii = self._message().replace("agent-collab-v4.1.0.plugin", "agent-collab-café.plugin")
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

    # ---- properties the cut_journal tests used to cover (orphaned by the split) ----

    def test_format_refuses_to_emit_what_parse_would_reject(self) -> None:
        """Pins "never emit what we would not accept".

        The round-trip test alone does NOT pin it: it only formats VALID input, so
        deleting the parse-before-return guard in format_tag_message passes silently.
        Each case here is rejected only because format re-parses its own output.
        """
        ok = dict(asset_name="agent-collab-v1.0.0.plugin",
                  asset_sha256=GOOD_ASSET, manifest_sha256=GOOD_MANIFEST)
        for label, over in (
            ("traversal asset name", {"asset_name": "../evil.plugin"}),
            ("nested asset name", {"asset_name": "dir/evil.plugin"}),
            ("uppercase digest", {"asset_sha256": GOOD_ASSET.upper()}),
            ("short digest", {"manifest_sha256": "a" * 63}),
            ("non-ascii asset name", {"asset_name": "agent-collab-café.plugin"}),
        ):
            with self.subTest(label=label):
                with self.assertRaises(self.rtc.TagContractError):
                    self.rtc.format_tag_message("v1.0.0", **{**ok, **over})

    def test_asset_name_charclass_is_enforced_independently(self) -> None:
        """Isolates _ASSET_NAME_RE from the slash and ASCII checks.

        Each name below is ASCII and slash-free, so it passes those two guards and
        can only be rejected by the character-class regex itself — otherwise the
        regex would be untested (the same overlap problem the mode guards had).
        """
        for bad in ("foo;evil.plugin", "foo|evil.plugin", "\x00.plugin",
                    ".hidden.plugin", "", "a" * 200):
            message = self._message().replace("Asset-Name: agent-collab-v4.1.0.plugin",
                                              f"Asset-Name: {bad}")
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(self.rtc.TagContractError):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")

    def test_validate_tag_name_security_properties(self) -> None:
        """Direct cases for the properties the docstring claims.

        These lived in the cut_journal tests until that module left this PR; without
        them the \\A/\\Z choice, the leading-zero rule and the traversal/injection
        rejections would be documented but unproven.
        """
        for bad, why in (
            ("v1.0.0\n", "trailing newline — `$` would accept this, `\\Z` must not"),
            ("v01.0.0", "leading zero — must not be a second name for v1.0.0"),
            ("v1.0.0/..", "path traversal"),
            ("v1.0.0:evil", "ref injection"),
            ("../v1.0.0", "traversal prefix"),
            ("", "empty"),
            ("v1.0", "incomplete"),
            (None, "non-string"),
        ):
            with self.subTest(why=why):
                with self.assertRaises(self.rtc.TagContractError):
                    self.rtc.validate_tag_name(bad)
        self.assertEqual(self.rtc.validate_tag_name("v1.0.0"), "v1.0.0")
        self.assertEqual(self.rtc.validate_tag_name("v0.0.0"), "v0.0.0")
        self.assertEqual(self.rtc.validate_tag_name("v10.20.30"), "v10.20.30")


    def test_canonical_field_ORDER_is_enforced_independently(self) -> None:
        """Isolates the order check: every field present and valid, only reordered.

        Without this, deleting the canonical-order check leaves the suite green — the
        other tests all use correctly-ordered messages, so the ordering rule was
        advertised but unproven.
        """
        good = self._message().rstrip("\n").split("\n")
        title, fields = good[0], good[1:]
        for i in range(len(fields) - 1):
            swapped = list(fields)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            message = "\n".join([title] + swapped) + "\n"
            with self.subTest(swap=i):
                with self.assertRaisesRegex(self.rtc.TagContractError, "canonical order"):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")

    def test_exactly_one_trailing_newline_is_enforced(self) -> None:
        """Isolates the final-newline rule: zero and two newlines both fail.

        Canonical form means one message, one byte sequence — accepting either
        variant would make distinct byte sequences validate as the same message.
        """
        body = self._message().rstrip("\n")
        for label, message in (("no trailing newline", body),
                               ("two trailing newlines", body + "\n\n"),
                               ("leading newline", "\n" + body + "\n")):
            with self.subTest(label=label):
                with self.assertRaises(self.rtc.TagContractError):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")

    def test_asset_names_must_be_portable(self) -> None:
        # A release asset may be materialized on any consumer platform: a trailing
        # dot or a Windows reserved device stem silently becomes a different file.
        for bad in ("CON", "NUL.plugin", "AUX", "COM1.plugin", "LPT9.plugin",
                    "trailing.", "name.."):
            message = self._message().replace("Asset-Name: agent-collab-v4.1.0.plugin",
                                              f"Asset-Name: {bad}")
            with self.subTest(bad=bad):
                with self.assertRaises(self.rtc.TagContractError):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")

    def test_oversized_input_is_bounded(self) -> None:
        # Bounds so oversized input fails cheaply, and so a tag can never exceed a
        # filesystem/ref component limit and fail deep inside a path operation.
        with self.assertRaisesRegex(self.rtc.TagContractError, "exceeds"):
            self.rtc.validate_tag_name("v1." + "9" * 80 + ".0")
        huge = self._message().rstrip("\n") + "\nAsset-Name: " + "a" * 8000 + "\n"
        with self.assertRaisesRegex(self.rtc.TagContractError, "exceeds"):
            self.rtc.parse_tag_message(huge, tag="v4.1.0")
        # ORDERING: the bound must be consulted BEFORE strip(). An oversized
        # all-whitespace message previously exited via the "empty" branch, having
        # scanned the whole object without the limit ever being applied — so the
        # error message here is the property, not incidental.
        with self.assertRaisesRegex(self.rtc.TagContractError, "exceeds"):
            self.rtc.parse_tag_message(" " * (self.rtc._MAX_MESSAGE_BYTES + 1), tag="v4.1.0")


    def test_asset_names_reject_characters_github_rewrites(self) -> None:
        """A space is not a cosmetic restriction — it breaks the receipt check.

        GitHub normalizes special characters in release-asset filenames, so an
        asset uploaded as "a b.plugin" is STORED under a different name than the
        tag signed. The v3 design compares the stored asset name to the signed
        one, so permitting a rewritten character would make a legitimate cut fail
        as a CONFLICT. The grammar therefore only admits characters GitHub keeps.
        """
        for bad in ("agent collab.plugin", "agent-collab v4.1.0.plugin", "a b"):
            message = self._message().replace("Asset-Name: agent-collab-v4.1.0.plugin",
                                              f"Asset-Name: {bad}")
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(self.rtc.TagContractError, "unsafe asset name"):
                    self.rtc.parse_tag_message(message, tag="v4.1.0")
        # ...and the real builder's name still round-trips.
        self.rtc.format_tag_message("v4.1.0", asset_name="agent-collab.plugin",
                                    asset_sha256=GOOD_ASSET, manifest_sha256=GOOD_MANIFEST)


    def test_every_rejection_is_a_TagContractError(self) -> None:
        """The parser's contract is TOTAL: no raw exception may escape.

        `encode()` on a lone surrogate raises UnicodeEncodeError, which would
        escape the contract — so ASCII is established before any encoding.
        """
        for bad, why in (("\ud800agent-collab v1.0.0\n", "lone surrogate"),
                         ("caf\u00e9\n", "non-ascii"),
                         ("\udcff" * 10 + "\n", "surrogate run")):
            with self.subTest(why=why):
                with self.assertRaises(self.rtc.TagContractError):
                    self.rtc.parse_tag_message(bad, tag="v1.0.0")

    def test_tag_length_bound_precedes_the_regex_scan(self) -> None:
        """ORDERING: a bound that runs after an unbounded scan is not a bound.

        An over-long AND syntactically-invalid tag must be rejected by the length
        guard ("exceeds"), not by the regex ("must be vMAJOR...") — which is only
        true if the length check runs first.
        """
        with self.assertRaisesRegex(self.rtc.TagContractError, "exceeds"):
            self.rtc.validate_tag_name("x" * 200)


if __name__ == "__main__":
    unittest.main()
