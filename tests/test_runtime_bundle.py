from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from tests._runtime_bundle_loader import rb


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/runtime_bundle_contract_v3.json"


class RuntimeBundleIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.records = cls.fixture["records"]

    def test_domain_separated_encoding_and_digest_match_fixed_fixture(self):
        encoded = rb.encode_bundle_identity(self.records)

        self.assertEqual(rb.IDENTITY_DOMAIN.decode("ascii"), self.fixture["identity_domain"])
        self.assertEqual(encoded.hex(), self.fixture["encoded_hex"])
        self.assertEqual(
            rb.compute_bundle_identity(self.records), self.fixture["artifact_sha256"]
        )

    def test_utf8_byte_sorting_is_mandatory_not_an_identity_alias(self):
        reversed_records = list(reversed(self.records))

        with self.assertRaisesRegex(rb.BundleContractError, "sorted"):
            rb.encode_bundle_identity(reversed_records)

    def test_each_encoded_field_changes_the_identity(self):
        mutations = {
            "path": "_ssl2.so",
            "role": "entrypoint",
            "install_mode": 0o400,
            "size": 32,
            "sha256": "33" * 32,
            "macho_type": "dylib",
            "architecture": "x86_64",
        }
        baseline = rb.compute_bundle_identity(self.records)
        for field, value in mutations.items():
            changed = copy.deepcopy(self.records)
            changed[0][field] = value
            changed.sort(key=lambda item: item["path"].encode("utf-8"))
            with self.subTest(field=field):
                try:
                    digest = rb.compute_bundle_identity(changed)
                except rb.BundleContractError:
                    continue
                self.assertNotEqual(digest, baseline)

    def test_record_schema_and_exact_integer_types_fail_closed(self):
        mutations = []

        def add(label, callback):
            value = copy.deepcopy(self.records)
            callback(value)
            mutations.append((label, value))

        add("unknown", lambda value: value[0].__setitem__("extra", 0))
        add("missing", lambda value: value[0].pop("sha256"))
        add("bool-mode", lambda value: value[0].__setitem__("install_mode", True))
        add("float-size", lambda value: value[0].__setitem__("size", 31.0))
        add("negative-size", lambda value: value[0].__setitem__("size", -1))
        add("digest-case", lambda value: value[0].__setitem__("sha256", "AA" * 32))
        add("unknown-role", lambda value: value[0].__setitem__("role", "helper"))
        add("unknown-macho", lambda value: value[0].__setitem__("macho_type", "object"))
        add("wrong-arch", lambda value: value[0].__setitem__("architecture", "x86_64"))
        add("wrong-minimum", lambda value: value[0].__setitem__("minimum_macos", "13.0"))
        add("wrong-profile", lambda value: value[0].__setitem__("signing_profile", "raw"))
        for label, records in mutations:
            with self.subTest(label=label):
                with self.assertRaises(rb.BundleContractError):
                    rb.validate_file_records(records)

    def test_path_normalization_confusables_and_representations_fail_closed(self):
        invalid_paths = (
            "",
            ".",
            "..",
            "/absolute",
            "nested/member",
            "nested\\member",
            "nested\u2215member",
            "nested\u2044member",
            "nested\uff0fmember",
            "line\nbreak",
            "nul\x00byte",
            "e\u0301.so",
        )
        for path in invalid_paths:
            records = copy.deepcopy(self.records)
            records[0]["path"] = path
            records.sort(key=lambda item: item["path"].encode("utf-8"))
            with self.subTest(path=repr(path)):
                with self.assertRaises(rb.BundleContractError):
                    rb.validate_file_records(records)

        duplicates = copy.deepcopy(self.records)
        duplicates[2]["path"] = duplicates[0]["path"].upper()
        duplicates.sort(key=lambda item: item["path"].encode("utf-8"))
        with self.assertRaisesRegex(rb.BundleContractError, "representation"):
            rb.validate_file_records(duplicates)

    def test_entrypoint_count_file_count_and_byte_budget_are_closed(self):
        no_entrypoint = copy.deepcopy(self.records)
        no_entrypoint[1]["role"] = "runtime_library"
        two_entrypoints = copy.deepcopy(self.records)
        two_entrypoints[0]["role"] = "entrypoint"
        oversized = copy.deepcopy(self.records)
        oversized[0]["size"] = rb.MAX_BUNDLE_BYTES
        too_many = []
        for index in range(rb.MAX_BUNDLE_FILES + 1):
            item = copy.deepcopy(self.records[0])
            item["path"] = f"lib-{index:03d}.so"
            too_many.append(item)
        for label, records in (
            ("no-entrypoint", no_entrypoint),
            ("two-entrypoints", two_entrypoints),
            ("oversized", oversized),
            ("too-many", too_many),
        ):
            records.sort(key=lambda item: item["path"].encode("utf-8"))
            with self.subTest(label=label):
                with self.assertRaises(rb.BundleContractError):
                    rb.validate_file_records(records)

    def test_role_and_macho_type_pairing_is_closed(self):
        cases = ((0, "executable"), (1, "dylib"))
        for index, replacement in cases:
            records = copy.deepcopy(self.records)
            records[index]["macho_type"] = replacement
            with self.subTest(index=index):
                with self.assertRaises(rb.BundleContractError):
                    rb.validate_file_records(records)


class RuntimeBundleJsonTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_and_nonobject_roots_fail_closed(self):
        invalid = (
            b'{"files":[],"files":[]}',
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":-Infinity}',
            b'[]',
            b'',
            b'\xff',
        )
        for raw in invalid:
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(rb.BundleContractError):
                    rb.load_closed_json_object(raw)

    def test_bounded_exact_object_is_accepted(self):
        self.assertEqual(rb.load_closed_json_object(b'{"schema_version":2}'), {
            "schema_version": 2,
        })


class RuntimeBundleTreeTests(unittest.TestCase):
    def _create_bundle(self, root: Path):
        contents = {
            "agent-collab-runtime": b"entrypoint",
            "libpython3.13.dylib": b"library",
        }
        records = []
        for path, data in contents.items():
            target = root / path
            target.write_bytes(data)
            target.chmod(0o500)
            records.append({
                "path": path,
                "role": "entrypoint" if path == "agent-collab-runtime" else "runtime_library",
                "install_mode": 0o500,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "macho_type": "executable" if path == "agent-collab-runtime" else "dylib",
                "architecture": "arm64",
                "minimum_macos": "14.0",
                "signing_profile": "development_adhoc",
            })
        records.sort(key=lambda item: item["path"].encode("utf-8"))
        root.chmod(0o500)
        return records

    @staticmethod
    def _inspector(path: Path):
        return {
            "macho_type": "executable" if path.name == "agent-collab-runtime" else "dylib",
            "architecture": "arm64",
            "minimum_macos": "14.0",
            "signing_profile": "development_adhoc",
        }

    def test_exact_regular_single_link_tree_is_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "agent-collab-runtime.bundle"
            root.mkdir()
            records = self._create_bundle(root)
            try:
                self.assertEqual(
                    rb.verify_bundle_tree(root, records, inspector=self._inspector),
                    rb.compute_bundle_identity(records),
                )
            finally:
                root.chmod(0o700)

    def test_host_normalized_root_with_strict_members_is_verified(self):
        # Regression lock for the REAL install state observed across EVERY host
        # manager (Claude Code, Codex, Antigravity/agy, and the broker's sealed
        # copies): install/autoUpdate normalizes the bundle DIRECTORY to 0o755
        # but leaves the member FILES at 0o500. The loader must accept this
        # (root-mode tolerance in _bundle_root_mode_ok + strict-0o500 members).
        #
        # This is the empirical refutation of the release-pipeline design-of-
        # record §9.7 premise ("host normalizes member files to 0o700"): a scan
        # of every installed bundle found 2356/2356 member files at 0o500 and
        # ZERO at 0o700, and resolve_runtime() returns OK on the real install.
        # No source-mode loosening is warranted (it would be unnecessary AND
        # would open a direct-execution-of-owner-writable-source bypass); this
        # test instead pins the already-correct behavior against regression.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "agent-collab-runtime.bundle"
            root.mkdir()
            records = self._create_bundle(root)  # member files 0o500
            root.chmod(0o755)  # host-normalized directory
            try:
                self.assertEqual(
                    rb.verify_bundle_tree(root, records, inspector=self._inspector),
                    rb.compute_bundle_identity(records),
                )
            finally:
                root.chmod(0o700)

    def test_symlink_hardlink_extra_missing_and_content_drift_fail_closed(self):
        mutations = ("symlink", "hardlink", "extra", "missing", "content")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "agent-collab-runtime.bundle"
                root.mkdir()
                records = self._create_bundle(root)
                root.chmod(0o700)
                target = root / "libpython3.13.dylib"
                if mutation == "symlink":
                    target.unlink()
                    target.symlink_to(root / "agent-collab-runtime")
                elif mutation == "hardlink":
                    target.unlink()
                    os.link(root / "agent-collab-runtime", target)
                elif mutation == "extra":
                    (root / "extra.dylib").write_bytes(b"extra")
                elif mutation == "missing":
                    target.unlink()
                else:
                    target.chmod(0o700)
                    target.write_bytes(b"changed")
                    target.chmod(0o500)
                root.chmod(0o500)
                try:
                    with self.assertRaises(rb.BundleContractError):
                        rb.verify_bundle_tree(root, records, inspector=self._inspector)
                finally:
                    root.chmod(0o700)

    def test_wrong_root_or_member_mode_and_inspection_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "agent-collab-runtime.bundle"
            root.mkdir()
            records = self._create_bundle(root)
            # A group-writable root is a genuinely unsafe mode and must still fail closed
            # (0o700 / host-normalized 0o755 are now ACCEPTED by the cache-stable predicate).
            root.chmod(0o775)
            with self.assertRaises(rb.BundleContractError):
                rb.verify_bundle_tree(root, records, inspector=self._inspector)
            root.chmod(0o500)

            def wrong_inspector(path: Path):
                facts = self._inspector(path)
                facts["architecture"] = "x86_64"
                return facts

            try:
                with self.assertRaises(rb.BundleContractError):
                    rb.verify_bundle_tree(root, records, inspector=wrong_inspector)
            finally:
                root.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
