"""Canonical agent-collab archive membership and parity contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import stat
import sys
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
SCRIPT = ROOT / "scripts" / "build_plugin_archive.py"
LEGAL_FILES = ("LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md")
THIRD_PARTY_NOTICE = "THIRD-PARTY-NOTICES.txt"
THIRD_PARTY_LICENSE_FILES = (
    "CPython-3.13.14-LICENSE.txt",
    "CPython-3.13.14-NOTICES.txt",
    "Expat-COPYING.txt",
    "HACL-LICENSE.txt",
    "Hedley-CC0-1.0.txt",
    "libb2-CC0-1.0.txt",
    "Nuitka-4.1.3-LICENSE-RUNTIME.txt",
    "Nuitka-4.1.3-LICENSE.txt",
    "Nuitka-4.1.3-NOTICE.txt",
    "mimalloc-LICENSE.txt",
    "mpdecimal-NOTICE.txt",
)


def _load():
    spec = importlib.util.spec_from_file_location("build_plugin_archive", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PluginArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = _load()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugins" / "agent-collab"
        shutil.copytree(
            PLUGIN,
            self.plugin,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runtime"),
        )
        self.archive = self.root / "agent-collab.plugin"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _install_third_party_notices(self) -> None:
        self.assertTrue((self.plugin / THIRD_PARTY_NOTICE).is_file())
        licenses = self.plugin / "third-party-licenses"
        for name in THIRD_PARTY_LICENSE_FILES:
            self.assertTrue((licenses / name).is_file())

    def _activate(self) -> Path:
        """Stage an activation manifest in-tree + a signed bundle OUT-of-tree.

        The runtime bundle ships as a release asset (never committed), so the
        fixture mirrors production: the committed tree carries only the
        manifest, and the 0o500 bundle leaf lives in an external handoff
        directory supplied to the builder via ``bundle_source``.
        """

        self._install_third_party_notices()
        self.bundle_leaf = (
            self.root / "handoff" / "agent-collab-runtime.bundle"
        )
        runtime = self.bundle_leaf / "agent-collab-runtime"
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b"signed-runtime-fixture")
        library = runtime.parent / "libpython3.13.dylib"
        library.write_bytes(b"signed-library-fixture")
        runtime.chmod(0o500)
        library.chmod(0o500)
        runtime.parent.chmod(0o500)
        records = []
        for member, role, macho_type in (
            (runtime, "entrypoint", "executable"),
            (library, "runtime_library", "dylib"),
        ):
            records.append(
                {
                    "path": member.name,
                    "role": role,
                    "install_mode": 0o500,
                    "size": member.stat().st_size,
                    "sha256": hashlib.sha256(member.read_bytes()).hexdigest(),
                    "macho_type": macho_type,
                    "architecture": "arm64",
                    "minimum_macos": "14.0",
                    "signing_profile": "production_developer_id",
                }
            )
        records.sort(key=lambda item: item["path"].encode("utf-8"))
        contracts = (
            ("gemini", "advisory"),
            ("gemini", "governance"),
            ("gemini", "long_context"),
            ("codex", "advisory"),
            ("opencode", "plan"),
            ("opencode", "build"),
            ("grok", "architecture"),
            ("grok", "governance"),
            ("grok", "huge_context"),
            ("composer", "codegen"),
        )
        manifest = {
            "schema_version": 2,
            "protocol_version": 1,
            "contract_version": 3,
            "broker_protocol_version": 2,
            "channel": "production",
            "artifacts": [
                {
                    "platform": "darwin",
                    "arch": "arm64",
                    "kind": "standalone_bundle",
                    "minimum_macos": "14.0",
                    "path": "runtime/darwin-arm64/agent-collab-runtime.bundle",
                    "entrypoint": "agent-collab-runtime",
                    "size": sum(record["size"] for record in records),
                    "sha256": self.builder.runtime_bundle.compute_bundle_identity(records),
                    "signing": {
                        "mode": "developer_id",
                        "identity": "Developer ID Application: Test Operator (TESTTEAM01)",
                        "team_id": "TESTTEAM01",
                        "require_notarization": True,
                        "hardened_runtime": True,
                        "secure_timestamp": True,
                    },
                    "files": records,
                    "contracts": [
                        {"route": route, "action": action}
                        for route, action in contracts
                    ],
                }
            ],
        }
        (self.plugin / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return runtime

    def test_policy_only_archive_includes_policy_and_omits_runtime(self) -> None:
        self._install_third_party_notices()
        mode = self.builder.build_archive(
            self.root, plugin="agent-collab", output=self.archive
        )
        self.assertEqual(mode, "policy-only")

        with tarfile.open(self.archive, "r:gz") as bundle:
            names = set(bundle.getnames())
            self.assertIn(".claude-plugin/plugin.json", names)
            self.assertIn(".codex-plugin/plugin.json", names)
            self.assertIn("runtime_client.py", names)
            self.assertIn("runtime_setup.py", names)
            self.assertIn("signing_policy.py", names)
            self.assertIn("runtime-manifest.json", names)
            for name in LEGAL_FILES:
                self.assertIn(name, names)
                member = bundle.getmember(name)
                self.assertEqual(
                    bundle.extractfile(member).read(),
                    (ROOT / name).read_bytes(),
                )
            self.assertFalse(any(name == "runtime" or name.startswith("runtime/") for name in names))
            self.assertNotIn(THIRD_PARTY_NOTICE, names)
            self.assertFalse(
                any(
                    name == "third-party-licenses"
                    or name.startswith("third-party-licenses/")
                    for name in names
                )
            )
            policy = bundle.getmember("signing_policy.py")
            self.assertEqual(
                stat.S_IMODE(policy.mode),
                stat.S_IMODE((self.plugin / "signing_policy.py").stat().st_mode),
            )
            self.assertEqual(
                bundle.extractfile(policy).read(),
                (self.plugin / "signing_policy.py").read_bytes(),
            )

    def test_packaged_legal_files_match_repository_canonicals(self) -> None:
        for name in LEGAL_FILES:
            self.assertTrue((ROOT / name).is_file(), f"missing root {name}")
            self.assertTrue((PLUGIN / name).is_file(), f"missing plugin {name}")
            self.assertEqual(
                (PLUGIN / name).read_bytes(),
                (ROOT / name).read_bytes(),
                name,
            )

    def test_activation_archive_has_exactly_one_runtime_with_byte_mode_parity(self) -> None:
        runtime = self._activate()
        mode = self.builder.build_archive(
            self.root,
            plugin="agent-collab",
            output=self.archive,
            bundle_source=self.bundle_leaf,
        )
        self.assertEqual(mode, "activation")

        bundle_prefix = "runtime/darwin-arm64/agent-collab-runtime.bundle/"
        with tarfile.open(self.archive, "r:gz") as bundle:
            runtime_files = [
                member
                for member in bundle.getmembers()
                if member.isfile() and member.name.startswith("runtime/")
            ]
            self.assertEqual(
                [member.name for member in runtime_files],
                [
                    bundle_prefix + "agent-collab-runtime",
                    bundle_prefix + "libpython3.13.dylib",
                ],
            )
            member = runtime_files[0]
            self.assertEqual(bundle.extractfile(member).read(), runtime.read_bytes())
            self.assertEqual(stat.S_IMODE(member.mode), 0o500)

            # Synthesized runtime directory scaffolding carries fixed canonical
            # modes: 0o755 traversal parents + the sealed 0o500 bundle leaf.
            directory_modes = {
                archived.name: stat.S_IMODE(archived.mode)
                for archived in bundle.getmembers()
                if archived.isdir() and archived.name.startswith("runtime")
            }
            self.assertEqual(
                directory_modes,
                {
                    "runtime": 0o755,
                    "runtime/darwin-arm64": 0o755,
                    "runtime/darwin-arm64/agent-collab-runtime.bundle": 0o500,
                },
            )

            for archived in bundle.getmembers():
                if not archived.isfile():
                    continue
                if archived.name.startswith(bundle_prefix):
                    source = self.bundle_leaf / archived.name[len(bundle_prefix):]
                else:
                    source = self.plugin / archived.name
                self.assertEqual(bundle.extractfile(archived).read(), source.read_bytes())
                self.assertEqual(
                    stat.S_IMODE(archived.mode),
                    stat.S_IMODE(source.stat().st_mode),
                )

    def test_activation_archive_includes_canonical_third_party_notice_tree(self) -> None:
        self._activate()
        mode = self.builder.build_archive(
            self.root,
            plugin="agent-collab",
            output=self.archive,
            bundle_source=self.bundle_leaf,
        )
        self.assertEqual(mode, "activation")

        with tarfile.open(self.archive, "r:gz") as bundle:
            names = bundle.getnames()
            expected = [
                THIRD_PARTY_NOTICE,
                "third-party-licenses",
                *(
                    f"third-party-licenses/{name}"
                    for name in THIRD_PARTY_LICENSE_FILES
                ),
            ]
            self.assertEqual(
                [
                    name
                    for name in names
                    if name == THIRD_PARTY_NOTICE
                    or name == "third-party-licenses"
                    or name.startswith("third-party-licenses/")
                ],
                sorted(expected),
            )
            for name in expected:
                member = bundle.getmember(name)
                source = self.plugin / name
                self.assertEqual(member.isfile(), source.is_file())
                self.assertEqual(member.isdir(), source.is_dir())
                if member.isfile():
                    self.assertEqual(bundle.extractfile(member).read(), source.read_bytes())

    def test_activation_rejects_missing_third_party_notice_member(self) -> None:
        self._activate()
        (self.plugin / "third-party-licenses" / THIRD_PARTY_LICENSE_FILES[0]).unlink()

        with self.assertRaisesRegex(ValueError, "third-party notice tree"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=self.bundle_leaf,
            )

    def test_activation_rejects_missing_top_level_third_party_notice(self) -> None:
        self._activate()
        (self.plugin / THIRD_PARTY_NOTICE).unlink()

        with self.assertRaisesRegex(ValueError, "third-party notice tree"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=self.bundle_leaf,
            )

    def test_activation_rejects_unexpected_third_party_notice_member(self) -> None:
        self._activate()
        (self.plugin / "third-party-licenses" / "unexpected.txt").write_text(
            "unexpected\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "third-party notice tree"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=self.bundle_leaf,
            )

    def test_activation_rejects_third_party_notice_content_drift(self) -> None:
        self._activate()
        source = self.plugin / "third-party-licenses" / THIRD_PARTY_LICENSE_FILES[0]
        source.write_text("tampered legal text\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "content digest"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=self.bundle_leaf,
            )

    def test_activation_rejects_symlinked_third_party_notice_member(self) -> None:
        self._activate()
        link = self.plugin / "third-party-licenses" / THIRD_PARTY_LICENSE_FILES[0]
        link.unlink()
        link.symlink_to(THIRD_PARTY_LICENSE_FILES[1])

        with self.assertRaisesRegex(ValueError, "unsafe|third-party notice tree"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=self.bundle_leaf,
            )

    def test_policy_only_rejects_unadvertised_runtime_and_missing_policy(self) -> None:
        runtime = (
            self.plugin
            / "runtime"
            / "darwin-arm64"
            / "agent-collab-runtime"
        )
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b"unadvertised")
        runtime.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "unadvertised runtime"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

        shutil.rmtree(self.plugin / "runtime")
        (self.plugin / "signing_policy.py").unlink()
        with self.assertRaisesRegex(ValueError, "signing_policy.py"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

    def test_archive_verifier_detects_source_byte_drift(self) -> None:
        mode = self.builder.build_archive(
            self.root, plugin="agent-collab", output=self.archive
        )
        policy = self.plugin / "signing_policy.py"
        original = policy.read_bytes()

        # Same-size drift: the regenerated canonical tar differs from the
        # candidate outside any runtime range → structural byte-compare fails.
        policy.write_bytes(b"#" * len(original))
        with self.assertRaisesRegex(ValueError, "structure does not match"):
            self.builder.verify_archive(self.plugin, self.archive, mode=mode)

        # Size drift changes the total canonical length → rejected up front.
        policy.write_bytes(original + b"\n# tail\n")
        with self.assertRaisesRegex(ValueError, "does not match the canonical layout"):
            self.builder.verify_archive(self.plugin, self.archive, mode=mode)

    def test_archive_size_limit_and_required_policy_member_are_canonical(self) -> None:
        self.assertEqual(self.builder.MAX_ARTIFACT_BYTES, 64 * 1024 * 1024)
        self.assertEqual(self.builder.RUNTIME_FILE_MODE, 0o500)
        self.assertIn("runtime_bundle.py", self.builder.REQUIRED_ROOTS)
        self.assertIn("signing_policy.py", self.builder.REQUIRED_ROOTS)
        self.assertIn("runtime_setup.py", self.builder.REQUIRED_ROOTS)

    def test_archive_fails_closed_when_runtime_setup_entrypoint_is_missing(self) -> None:
        (self.plugin / "runtime_setup.py").unlink()
        with self.assertRaisesRegex(
            ValueError, "required archive member is missing: runtime_setup.py"
        ):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

    def _build_activation(self) -> str:
        return self.builder.build_archive(
            self.root,
            plugin="agent-collab",
            output=self.archive,
            bundle_source=self.bundle_leaf,
        )

    def test_activation_manifest_requires_bundle_source_fail_closed(self) -> None:
        self._activate()
        with self.assertRaisesRegex(ValueError, "requires --bundle-source"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )
        self.assertFalse(self.archive.exists())

    def test_policy_only_manifest_forbids_bundle_source(self) -> None:
        self._install_third_party_notices()
        stray = self.root / "stray-bundle"
        stray.mkdir()
        with self.assertRaisesRegex(ValueError, "forbids --bundle-source"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=stray,
            )

    def test_in_tree_runtime_conflicts_with_bundle_source(self) -> None:
        self._activate()
        (self.plugin / "runtime").mkdir()
        with self.assertRaisesRegex(ValueError, "in-tree runtime conflicts"):
            self._build_activation()

    def test_bundle_source_rejects_symlink_argument_before_resolve(self) -> None:
        self._activate()
        alias = self.root / "leaf-alias"
        alias.symlink_to(self.bundle_leaf)
        with self.assertRaisesRegex(ValueError, "runtime bundle source is unsafe"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=self.archive,
                bundle_source=alias,
            )

    def test_bundle_source_rejects_content_and_size_drift(self) -> None:
        self._activate()
        library = self.bundle_leaf / "libpython3.13.dylib"
        original = library.read_bytes()

        library.chmod(0o700)
        library.write_bytes(b"X" * len(original))  # same size, wrong bytes
        library.chmod(0o500)
        with self.assertRaisesRegex(ValueError, "digest is invalid"):
            self._build_activation()

        library.chmod(0o700)
        library.write_bytes(original + b"tail")  # size drift
        library.chmod(0o500)
        with self.assertRaisesRegex(ValueError, "member identity is invalid"):
            self._build_activation()
        self.assertFalse(self.archive.exists())

    def test_bundle_source_rejects_mode_drift(self) -> None:
        self._activate()
        (self.bundle_leaf / "libpython3.13.dylib").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "member identity is invalid"):
            self._build_activation()

        (self.bundle_leaf / "libpython3.13.dylib").chmod(0o500)
        self.bundle_leaf.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "root identity is invalid"):
            self._build_activation()

    def test_bundle_source_requires_exact_membership(self) -> None:
        self._activate()
        self.bundle_leaf.chmod(0o700)
        extra = self.bundle_leaf / "extra-member"
        extra.write_bytes(b"unexpected")
        self.bundle_leaf.chmod(0o500)
        with self.assertRaisesRegex(ValueError, "membership is not exact"):
            self._build_activation()

        self.bundle_leaf.chmod(0o700)
        extra.unlink()
        (self.bundle_leaf / "libpython3.13.dylib").unlink()
        self.bundle_leaf.chmod(0o500)
        with self.assertRaisesRegex(ValueError, "membership is not exact"):
            self._build_activation()

    def test_bundle_source_rejects_symlinked_member(self) -> None:
        self._activate()
        self.bundle_leaf.chmod(0o700)
        library = self.bundle_leaf / "libpython3.13.dylib"
        library.unlink()
        library.symlink_to("agent-collab-runtime")
        self.bundle_leaf.chmod(0o500)
        with self.assertRaisesRegex(
            ValueError, "member is unsafe|member identity is invalid"
        ):
            self._build_activation()

    def test_bundle_source_rejects_hardlinked_member(self) -> None:
        self._activate()
        os.link(
            self.bundle_leaf / "agent-collab-runtime",
            self.root / "hardlink-aside",
        )
        with self.assertRaisesRegex(ValueError, "member identity is invalid"):
            self._build_activation()

    def test_failed_verification_leaves_no_output_artifact(self) -> None:
        self._activate()
        with mock.patch.object(
            self.builder, "verify_archive", side_effect=ValueError("forced failure")
        ):
            with self.assertRaisesRegex(ValueError, "forced failure"):
                self._build_activation()
        self.assertFalse(self.archive.exists())
        leftovers = [
            path.name
            for path in self.archive.parent.iterdir()
            if ".tmp" in path.name
        ]
        self.assertEqual(leftovers, [])

    def test_verify_archive_binds_runtime_bytes_to_frozen_manifest(self) -> None:
        self._activate()
        mode = self._build_activation()
        target = "runtime/darwin-arm64/agent-collab-runtime.bundle/agent-collab-runtime"

        # Repack the archive swapping the runtime member's bytes for same-size
        # garbage while keeping every member's metadata identical: source
        # parity cannot notice (the source tree is untouched), only the frozen
        # manifest digest binding can.
        tampered = self.root / "tampered.plugin"
        with tarfile.open(self.archive, "r:gz") as original:
            members = [
                (member, original.extractfile(member).read() if member.isfile() else None)
                for member in original.getmembers()
            ]
        import gzip as gzip_module

        with tampered.open("wb") as raw:
            with gzip_module.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
                ) as bundle:
                    for member, payload in members:
                        if member.name == target:
                            payload = b"Y" * member.size
                        if payload is None:
                            bundle.addfile(member)
                        else:
                            import io

                            bundle.addfile(member, io.BytesIO(payload))

        with self.assertRaisesRegex(ValueError, "runtime member digest failed"):
            self.builder.verify_archive(self.plugin, tampered, mode=mode)

    def test_verify_archive_binds_archived_manifest_to_frozen_bytes(self) -> None:
        self._activate()
        mode = self._build_activation()
        manifest_path = self.plugin / "runtime-manifest.json"
        # A SAME-SIZE, parse-valid, record-preserving byte change after the
        # build (identity string tweak): the archived manifest member is a
        # non-runtime member, so the regenerated canonical (embedding the new
        # on-disk bytes) differs from the candidate → structural compare fails.
        text = manifest_path.read_text(encoding="utf-8")
        swapped = text.replace("Test Operator", "Test Operatox")
        self.assertNotEqual(text, swapped)
        self.assertEqual(len(text), len(swapped))
        manifest_path.write_text(swapped, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "structure does not match"):
            self.builder.verify_archive(self.plugin, self.archive, mode=mode)

        # A size-changing swap changes the canonical total length → rejected.
        manifest_path.write_text(text + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match the canonical layout"):
            self.builder.verify_archive(self.plugin, self.archive, mode=mode)

    def test_verify_archive_rejects_non_canonical_member_metadata(self) -> None:
        self._activate()
        mode = self._build_activation()
        target = "signing_policy.py"

        # Repack with one member's mtime perturbed while bytes/modes stay
        # identical: source parity cannot notice, only the canonical-metadata
        # contract can.
        tampered = self.root / "tampered-metadata.plugin"
        import gzip as gzip_module
        import io

        with tarfile.open(self.archive, "r:gz") as original:
            members = [
                (member, original.extractfile(member).read() if member.isfile() else None)
                for member in original.getmembers()
            ]
        with tampered.open("wb") as raw:
            with gzip_module.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
                ) as bundle:
                    for member, payload in members:
                        if member.name == target:
                            member.mtime = 1
                        if payload is None:
                            bundle.addfile(member)
                        else:
                            bundle.addfile(member, io.BytesIO(payload))

        with self.assertRaisesRegex(ValueError, "structure does not match|canonical layout"):
            self.builder.verify_archive(self.plugin, tampered, mode=mode)

    def test_failed_exclusive_temp_open_preserves_foreign_file(self) -> None:
        self._activate()
        # Pre-create the exact temp path this invocation would claim: the
        # O_EXCL open must fail AND the foreign file must survive untouched.
        foreign = (
            self.archive.parent / f".{self.archive.name}.tmp.{os.getpid()}"
        )
        foreign.write_bytes(b"foreign artifact")
        with self.assertRaises(OSError):
            self._build_activation()
        self.assertEqual(foreign.read_bytes(), b"foreign artifact")
        self.assertFalse(self.archive.exists())

    def test_output_alias_of_source_trees_is_rejected(self) -> None:
        self._activate()
        for alias in (
            self.plugin / "aliased-output.plugin",
            self.bundle_leaf / "aliased-output.plugin",
        ):
            with self.subTest(alias=str(alias)):
                with self.assertRaisesRegex(ValueError, "alias a source tree"):
                    self.builder.build_archive(
                        self.root,
                        plugin="agent-collab",
                        output=alias,
                        bundle_source=self.bundle_leaf,
                    )
        # A symlinked parent that resolves into a source tree is caught too.
        symdir = self.root / "sym-parent"
        symdir.symlink_to(self.plugin)
        with self.assertRaisesRegex(ValueError, "alias a source tree"):
            self.builder.build_archive(
                self.root,
                plugin="agent-collab",
                output=symdir / "aliased-output.plugin",
                bundle_source=self.bundle_leaf,
            )
        self.assertFalse((self.plugin / "aliased-output.plugin").exists())

    def test_pack_time_failure_leaves_no_output_or_temp(self) -> None:
        self._activate()
        with mock.patch.object(
            self.builder,
            "_synthesized_tarinfo",
            side_effect=OSError("forced pack failure"),
        ):
            with self.assertRaises(OSError):
                self._build_activation()
        self.assertFalse(self.archive.exists())
        leftovers = [
            path.name
            for path in self.archive.parent.iterdir()
            if ".tmp" in path.name
        ]
        self.assertEqual(leftovers, [])

    def test_cli_builds_activation_archive_with_bundle_source(self) -> None:
        self._activate()
        exit_code = self.builder.main(
            [
                "--repo-root",
                str(self.root),
                "--output",
                str(self.archive),
                "--bundle-source",
                str(self.bundle_leaf),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(self.archive.is_file())
        self.builder.verify_archive(self.plugin, self.archive, mode="activation")

    def test_verify_bounds_hostile_archive_decompression(self) -> None:
        self._activate()
        mode = self._build_activation()

        # A gzip bomb (tiny compressed, huge decompressed) with a CANONICAL
        # header (mtime=0) must be rejected by the hard decompression bound,
        # not materialized.
        import gzip as gzip_module

        bomb = self.root / "bomb.plugin"
        with bomb.open("wb") as raw:
            # filename="" so no FNAME flag is set (canonical header), matching
            # what the builder's os.fdopen path emits.
            with gzip_module.GzipFile(
                filename="", fileobj=raw, mode="wb", mtime=0
            ) as stream:
                zero_chunk = b"\0" * (1024 * 1024)
                for _ in range(2 * 64 + 8):  # > 2 * MAX_ARTIFACT_BYTES
                    stream.write(zero_chunk)
        with self.assertRaisesRegex(ValueError, "decompression exceeds"):
            self.builder.verify_archive(self.plugin, bomb, mode=mode)

        # A non-canonical gzip header (non-zero mtime) is rejected up front.
        stamped = self.root / "stamped.plugin"
        with stamped.open("wb") as raw:
            with gzip_module.GzipFile(
                fileobj=raw, mode="wb", mtime=1_700_000_000
            ) as stream:
                stream.write(b"whatever")
        with self.assertRaisesRegex(ValueError, "gzip header is not canonical"):
            self.builder.verify_archive(self.plugin, stamped, mode=mode)

        # A symlinked archive path is refused outright.
        alias = self.root / "archive-alias.plugin"
        alias.symlink_to(self.archive)
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.builder.verify_archive(self.plugin, alias, mode=mode)

    def test_ustar_serializer_is_golden_across_python_versions(self) -> None:
        # Design item 5: the regenerate-and-compare architecture requires the
        # USTAR serializer to be byte-identical in the operator's build env
        # (3.13.14) and CI (3.10/3.12/3.14). This golden binds the exact bytes;
        # CI's version matrix fails here if any Python serializes USTAR
        # differently, so a legitimate cross-env archive can never fail the
        # verify byte-compare undetected.
        buffer = io.BytesIO()
        with tarfile.open(
            fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT
        ) as tar:
            tar.addfile(
                self.builder._synthesized_tarinfo(
                    "runtime/darwin-arm64/agent-collab-runtime.bundle",
                    mode=0o500,
                    directory=True,
                )
            )
            tar.addfile(
                self.builder._synthesized_tarinfo(
                    "runtime/darwin-arm64/agent-collab-runtime.bundle/agent-collab-runtime",
                    mode=0o500,
                    size=5,
                ),
                io.BytesIO(b"hello"),
            )
        data = buffer.getvalue()
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "366c3a87cf260b77a3c937b6c44ad6f91d91f1073d59d195a9ae761ec66b6bd0",
        )

    def test_canonical_tar_is_byte_reproducible_across_calls(self) -> None:
        # Design item 5: the canonical inflated tar must be byte-identical on
        # regeneration (the cross-environment reproducibility contract the
        # regenerate-and-compare architecture depends on). CI runs this on
        # 3.10/3.12/3.14, so a serializer-version divergence would fail here.
        self._activate()
        plugin = self.plugin.resolve(strict=True)
        frozen = self.builder._read_manifest_bytes(plugin)
        records = self.builder.runtime_bundle.validate_file_records(
            self.builder._parse_manifest(frozen)["artifacts"][0]["files"]
        )
        plan = self.builder._member_plan(plugin, mode="activation", records=records)
        rbn = {
            (self.builder.RUNTIME_BUNDLE_REL / r["path"]).as_posix(): r
            for r in records
        }
        zero = {name: b"\x00" * r["size"] for name, r in rbn.items()}
        first, ranges_a = self.builder._emit_canonical_tar(
            plan, plugin_path=plugin, frozen_manifest=frozen,
            record_by_name=rbn, runtime_payloads=zero,
        )
        second, ranges_b = self.builder._emit_canonical_tar(
            plan, plugin_path=plugin, frozen_manifest=frozen,
            record_by_name=rbn, runtime_payloads=zero,
        )
        self.assertEqual(first, second)
        self.assertEqual(ranges_a, ranges_b)
        # The reported ranges are one-to-one with the manifest, disjoint, and
        # in-bounds (item 6).
        self.builder._assert_runtime_range_map(ranges_a, rbn, len(first))

    def test_verify_rejects_raw_structural_tamper_without_parsing(self) -> None:
        # A hostile archive whose runtime payload digest is preserved but whose
        # STRUCTURE differs (here: a directory member's mode flipped) must be
        # rejected by the byte-compare, with no reliance on tarfile parsing the
        # candidate. We tamper the inflated tar bytes directly.
        self._activate()
        mode = self._build_activation()
        raw = self.archive.read_bytes()
        import gzip as gzip_module

        inflated = gzip_module.decompress(raw)
        # Flip one byte inside the first 512-byte header block (the manifest or
        # first member's metadata region) — a structural mutation.
        tampered_tar = bytearray(inflated)
        tampered_tar[100] ^= 0x01
        tampered = self.root / "raw-tamper.plugin"
        with tampered.open("wb") as fh:
            with gzip_module.GzipFile(
                filename="", fileobj=fh, mode="wb", mtime=0
            ) as gz:
                gz.write(bytes(tampered_tar))
        with self.assertRaisesRegex(
            ValueError, "structure does not match|canonical layout"
        ):
            self.builder.verify_archive(self.plugin, tampered, mode=mode)

    def test_activation_archive_build_is_deterministic(self) -> None:
        self._activate()
        self._build_activation()
        second = self.root / "agent-collab-second.plugin"
        self.builder.build_archive(
            self.root,
            plugin="agent-collab",
            output=second,
            bundle_source=self.bundle_leaf,
        )
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())

    def test_archive_rejects_unexpected_manifest_and_skill_members(self) -> None:
        extra_manifest = self.plugin / ".claude-plugin" / "extra.dat"
        extra_manifest.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest tree is not canonical"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

        extra_manifest.unlink()
        helper = self.plugin / "skills" / "route" / "helper.py"
        helper.write_text("pass", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "skill tree is not canonical"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )


if __name__ == "__main__":
    unittest.main()
