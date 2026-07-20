"""Signed-tag grammar + release-commit topology contract (fail-closed)."""

from __future__ import annotations

import importlib.util
import json
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


class ReleaseCommitTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rtc = _load()

    ARTIFACT = {"platform": "darwin-arm64", "sha256": "c" * 64,
                "size_bytes": 1234, "runtime_identity": "agent-collab-runtime 4.1.0"}

    def _manifests(self, *, artifacts_after=1, extra_change=False, artifact=None):
        base = {"schema_version": 2, "channel": "production", "artifacts": []}
        after = dict(base)
        # `is not None`, not `or`: an empty-dict artifact is a case under test,
        # and `artifact or DEFAULT` would silently swap in the valid one — the
        # helper would then quietly test the opposite of what it claims.
        chosen = self.ARTIFACT if artifact is None else artifact
        after["artifacts"] = [chosen] * artifacts_after
        if extra_change:
            after["channel"] = "beta"
        return json.dumps(base), json.dumps(after)

    def test_artifact_content_is_pinned_not_merely_counted(self) -> None:
        """A length-1 list is not a described artifact.

        `{"artifacts": [{}]}` and `{"artifacts": ["attacker-controlled"]}` both
        have length one, so a count-only gate binds the tag's Manifest-SHA256 to
        a manifest that describes nothing. Each case is rejected on its own.
        """
        before, _ = self._manifests()
        cases = [
            ({}, "missing required"),
            ({"platform": "darwin-arm64"}, "missing required"),
            (dict(self.ARTIFACT, sha256="C" * 64), "64 lowercase hex"),
            (dict(self.ARTIFACT, sha256="abc"), "64 lowercase hex"),
            (dict(self.ARTIFACT, size_bytes=0), "positive integer"),
            (dict(self.ARTIFACT, size_bytes="1234"), "positive integer"),
            # bool subclasses int, so `size_bytes: true` satisfies an
            # isinstance check and compares equal to 1.
            (dict(self.ARTIFACT, size_bytes=True), "positive integer"),
        ]
        for artifact, expected in cases:
            _, after = self._manifests(artifact=artifact)
            with self.subTest(artifact=artifact):
                with self.assertRaisesRegex(self.rtc.TagContractError, expected):
                    self.rtc.assert_release_commit_delta(
                        [self.rtc.MANIFEST_PATH],
                        parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")
        _, after = self._manifests(artifact="attacker-controlled")
        with self.assertRaisesRegex(self.rtc.TagContractError, "must be a JSON object"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_artifact_must_equal_the_one_derived_from_the_archive(self) -> None:
        # A well-formed artifact describing a DIFFERENT archive must not pass.
        before, after = self._manifests()
        self.rtc.assert_release_commit_delta(
            [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
            expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")
        with self.assertRaisesRegex(self.rtc.TagContractError, "does not match"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=dict(self.ARTIFACT, sha256="d" * 64),
                parent_mode="100644", release_mode="100644")

    def test_manifest_file_mode_is_part_of_the_topology(self) -> None:
        """An executable-bit flip must not ride along with a release.

        Paths and JSON alone cannot see mode, so a commit changing
        runtime-manifest.json from 100644 to 100755 while inserting the artifact
        would otherwise satisfy a gate that claims to pin exact topology.
        """
        before, after = self._manifests()
        with self.assertRaisesRegex(self.rtc.TagContractError, "file mode"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100755")
        # ISOLATES the change-guard: 100755 -> 100644 ends at the expected mode,
        # so the wrong-mode guard cannot catch it. Without this case the
        # change-guard survives deletion (the other guard covers the obvious
        # direction) and the test proves less than it appears to.
        with self.assertRaisesRegex(self.rtc.TagContractError, "changed the manifest file mode"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100755", release_mode="100644")
        # An unchanged-but-wrong mode is refused too, not just a change.
        with self.assertRaisesRegex(self.rtc.TagContractError, "must be 100644"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100755", release_mode="100755")

    def test_json_parser_divergence_is_refused_not_resolved(self) -> None:
        """Duplicate keys and NaN/Infinity are refused, not silently resolved.

        `json.loads` keeps the LAST duplicate and accepts non-standard constants;
        another reader may disagree. A downstream consumer trusts the tag's
        Manifest-SHA256 over these same bytes, so a manifest two parsers read
        differently must never pass — resolving the ambiguity quietly IS the bug.
        """
        before, _ = self._manifests()
        dup = ('{"schema_version": 2, "channel": "production", '
               '"channel": "beta", "artifacts": []}')
        with self.assertRaisesRegex(self.rtc.TagContractError, "duplicate key"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=dup, release_manifest=dup,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")
        nan = '{"schema_version": NaN, "artifacts": []}'
        with self.assertRaisesRegex(self.rtc.TagContractError, "non-standard constant"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=nan, release_manifest=before,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_exact_artifacts_insertion_is_accepted(self) -> None:
        before, after = self._manifests()
        self.rtc.assert_release_commit_delta(
            [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_forbidden_paths_hit_their_own_rule_not_the_generic_one(self) -> None:
        # The forbidden-prefix gate must be INDEPENDENT of the exact-match gate.
        # If it ran after the exact-match check it could never fire (the only
        # surviving path would be the manifest) — dead code masquerading as
        # defence in depth. Asserting the specific message proves it runs first.
        before, after = self._manifests()
        for extra in (".github/workflows/release.yml", ".gpgkeys/pinned.asc",
                      "scripts/cut_release.py",
                      "plugins/agent-collab/runtime/darwin-arm64/x.bundle/lib"):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(self.rtc.TagContractError, "must never touch"):
                    self.rtc.assert_release_commit_delta(
                        [self.rtc.MANIFEST_PATH, extra],
                        parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_any_other_extra_path_is_rejected_by_the_exact_match_gate(self) -> None:
        before, after = self._manifests()
        with self.assertRaisesRegex(self.rtc.TagContractError, "exactly"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH, "README.md"],
                parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_empty_diff_is_rejected(self) -> None:
        before, after = self._manifests()
        with self.assertRaises(self.rtc.TagContractError):
            self.rtc.assert_release_commit_delta(
                [], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_parent_already_carrying_artifacts_is_rejected(self) -> None:
        # main must NEVER carry activation artifacts (per-release, not per-branch).
        before = json.dumps({"schema_version": 2, "artifacts": [{"platform": "darwin"}]})
        after = json.dumps({"schema_version": 2, "artifacts": [{"platform": "darwin"}]})
        with self.assertRaisesRegex(self.rtc.TagContractError, "main must never carry"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_semantic_gate_catches_a_smuggled_field_change(self) -> None:
        # The whole point of a SEMANTIC delta: the path list is identical, so a
        # path-count check would pass — only comparing the non-artifacts fields
        # catches a channel/version flip riding along with the release commit.
        before, after = self._manifests(extra_change=True)
        with self.assertRaisesRegex(self.rtc.TagContractError, "other than 'artifacts'"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_must_add_exactly_one_artifact(self) -> None:
        for count in (0, 2):
            before, after = self._manifests(artifacts_after=count)
            with self.subTest(count=count):
                with self.assertRaisesRegex(self.rtc.TagContractError, "exactly one"):
                    self.rtc.assert_release_commit_delta(
                        [self.rtc.MANIFEST_PATH],
                        parent_manifest=before, release_manifest=after,
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")

    def test_malformed_manifest_json_fails_closed(self) -> None:
        with self.assertRaisesRegex(self.rtc.TagContractError, "not valid JSON"):
            self.rtc.assert_release_commit_delta(
                [self.rtc.MANIFEST_PATH], parent_manifest="{", release_manifest="{}",
                expected_artifact=self.ARTIFACT,
                parent_mode="100644", release_mode="100644")


if __name__ == "__main__":
    unittest.main()
