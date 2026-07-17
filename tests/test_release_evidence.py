"""Deterministic checksum and SPDX evidence for release archives."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_VERSION = json.loads(
    (
        ROOT
        / "plugins"
        / "agent-collab"
        / ".claude-plugin"
        / "plugin.json"
    ).read_text(encoding="utf-8")
)["version"]
ARCHIVE_SCRIPT = ROOT / "scripts" / "build_plugin_archive.py"
EVIDENCE_SCRIPT = ROOT / "scripts" / "build_release_evidence.py"
LEGAL_FILES = {"LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md"}
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


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / f"agent-collab v{PACKAGE_VERSION}.plugin"
        self.sbom = self.root / f"agent-collab-v{PACKAGE_VERSION}.spdx.json"
        self.checksum = self.root / f"agent-collab v{PACKAGE_VERSION}.plugin.sha256"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _build(self):
        self.assertTrue(
            EVIDENCE_SCRIPT.is_file(),
            "scripts/build_release_evidence.py must exist",
        )
        archive_builder = _load("agent_collab_archive_for_evidence", ARCHIVE_SCRIPT)
        evidence_builder = _load("agent_collab_release_evidence", EVIDENCE_SCRIPT)
        mode = archive_builder.build_archive(
            ROOT, plugin="agent-collab", output=self.archive
        )
        self.assertEqual(mode, "policy-only")
        evidence_builder.build_evidence(
            self.archive,
            version=PACKAGE_VERSION,
            created="2026-07-12T00:00:00Z",
            sbom_output=self.sbom,
            checksum_output=self.checksum,
            repo_root=ROOT,
        )
        return json.loads(self.sbom.read_text(encoding="utf-8"))

    def _build_activation(self):
        archive_builder = _load(
            "agent_collab_archive_activation_evidence", ARCHIVE_SCRIPT
        )
        evidence_builder = _load(
            "agent_collab_release_activation_evidence", EVIDENCE_SCRIPT
        )
        repo = self.root / "repo"
        plugin = repo / "plugins" / "agent-collab"
        shutil.copytree(
            ROOT / "plugins" / "agent-collab",
            plugin,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runtime"),
        )
        for name in LEGAL_FILES:
            shutil.copy2(ROOT / name, repo / name)
        # The signed bundle ships as a release asset (never committed): the
        # fixture stages it OUT-of-tree and supplies it via bundle_source.
        bundle = self.root / "handoff" / "agent-collab-runtime.bundle"
        bundle.mkdir(parents=True)
        runtime_members = {
            "agent-collab-runtime": (
                b"signed-runtime-entrypoint-fixture",
                "entrypoint",
                "executable",
            ),
            "libpython3.13.dylib": (
                b"signed-runtime-library-fixture",
                "runtime_library",
                "dylib",
            ),
        }
        records = []
        for name, (payload, role, macho_type) in runtime_members.items():
            member = bundle / name
            member.write_bytes(payload)
            member.chmod(0o500)
            records.append(
                {
                    "path": name,
                    "role": role,
                    "install_mode": 0o500,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "macho_type": macho_type,
                    "architecture": "arm64",
                    "minimum_macos": "14.0",
                    "signing_profile": "production_developer_id",
                }
            )
        bundle.chmod(0o500)
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
                    "sha256": archive_builder.runtime_bundle.compute_bundle_identity(
                        records
                    ),
                    "signing": {
                        "mode": "developer_id",
                        "identity": (
                            "Developer ID Application: Example Corp (TESTTEAM01)"
                        ),
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
        (plugin / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        mode = archive_builder.build_archive(
            repo,
            plugin="agent-collab",
            output=self.archive,
            bundle_source=bundle,
        )
        self.assertEqual(mode, "activation")
        evidence_builder.build_evidence(
            self.archive,
            version=PACKAGE_VERSION,
            created="2026-07-12T00:00:00Z",
            sbom_output=self.sbom,
            checksum_output=self.checksum,
            repo_root=repo,
        )
        return json.loads(self.sbom.read_text(encoding="utf-8"))

    def test_spdx_inventory_contains_exact_legal_files_and_license(self) -> None:
        sbom = self._build()

        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["dataLicense"], "CC0-1.0")
        self.assertEqual(sbom["creationInfo"]["created"], "2026-07-12T00:00:00Z")
        package = sbom["packages"][0]
        self.assertEqual(package["versionInfo"], PACKAGE_VERSION)
        self.assertEqual(
            package["licenseDeclared"],
            "LicenseRef-PolyForm-Strict-1.0.0",
        )
        self.assertEqual(package["licenseConcluded"], package["licenseDeclared"])
        files = {item["fileName"]: item for item in sbom["files"]}
        self.assertTrue(LEGAL_FILES <= set(files))
        extracted = sbom["hasExtractedLicensingInfos"]
        self.assertEqual(len(extracted), 1)
        self.assertEqual(
            extracted[0]["licenseId"],
            "LicenseRef-PolyForm-Strict-1.0.0",
        )
        self.assertEqual(extracted[0]["extractedText"], (ROOT / "LICENSE").read_text())

    def test_policy_only_spdx_output_preserves_project_only_license_contract(self) -> None:
        sbom = self._build()

        self.assertEqual(
            [package["name"] for package in sbom["packages"]],
            ["agent-collab"],
        )
        self.assertTrue(sbom["files"])
        self.assertTrue(
            all(
                item["licenseConcluded"]
                == "LicenseRef-PolyForm-Strict-1.0.0"
                for item in sbom["files"]
            )
        )

    def test_activation_spdx_identifies_runtime_components_and_file_licenses(self) -> None:
        sbom = self._build_activation()

        packages = {package["name"]: package for package in sbom["packages"]}
        self.assertEqual(
            set(packages),
            {
                "agent-collab",
                "CPython",
                "Nuitka",
                "expat",
                "hacl-star",
                "libb2",
                "mpdecimal",
                "mimalloc",
                "Hedley",
            },
        )
        self.assertEqual(packages["CPython"]["versionInfo"], "3.13.14")
        self.assertEqual(packages["CPython"]["licenseDeclared"], "Python-2.0")
        self.assertEqual(packages["Nuitka"]["versionInfo"], "4.1.3")
        self.assertEqual(packages["Nuitka"]["licenseDeclared"], "NOASSERTION")
        self.assertEqual(packages["expat"]["licenseDeclared"], "MIT")
        self.assertEqual(
            packages["hacl-star"]["licenseDeclared"], "MIT AND Apache-2.0"
        )
        self.assertEqual(packages["libb2"]["licenseDeclared"], "CC0-1.0")
        self.assertEqual(packages["mpdecimal"]["licenseDeclared"], "BSD-2-Clause")
        self.assertEqual(packages["mimalloc"]["licenseDeclared"], "MIT")
        self.assertEqual(packages["Hedley"]["licenseDeclared"], "CC0-1.0")

        files = {item["fileName"]: item for item in sbom["files"]}
        self.assertEqual(
            files["README.md"]["licenseConcluded"],
            "LicenseRef-PolyForm-Strict-1.0.0",
        )
        for name in (
            "agent-collab-runtime",
            "libpython3.13.dylib",
        ):
            self.assertEqual(
                files[
                    "runtime/darwin-arm64/agent-collab-runtime.bundle/" + name
                ]["licenseConcluded"],
                "NOASSERTION",
            )
        self.assertEqual(files[THIRD_PARTY_NOTICE]["licenseConcluded"], "NOASSERTION")
        for name in THIRD_PARTY_LICENSE_FILES:
            self.assertEqual(
                files[f"third-party-licenses/{name}"]["licenseConcluded"],
                "NOASSERTION",
            )

        relationships = {
            (
                relationship["spdxElementId"],
                relationship["relationshipType"],
                relationship["relatedSpdxElement"],
            )
            for relationship in sbom["relationships"]
        }
        self.assertIn(
            (
                "SPDXRef-Package-agent-collab",
                "CONTAINS",
                "SPDXRef-Package-CPython",
            ),
            relationships,
        )
        self.assertIn(
            (
                "SPDXRef-Package-agent-collab",
                "CONTAINS",
                "SPDXRef-Package-Nuitka",
            ),
            relationships,
        )

    def test_every_spdx_file_sha256_checksum_matches_archive_bytes(self) -> None:
        sbom = self._build()
        archived = self._archive_bytes()
        for item in sbom["files"]:
            checksums = {
                checksum["algorithm"]: checksum["checksumValue"]
                for checksum in item["checksums"]
            }
            self.assertEqual(
                checksums["SHA256"],
                hashlib.sha256(archived[item["fileName"]]).hexdigest(),
            )

    def _archive_bytes(self) -> dict[str, bytes]:
        archived: dict[str, bytes] = {}
        with tarfile.open(self.archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                if not member.isfile():
                    continue
                stream = bundle.extractfile(member)
                self.assertIsNotNone(stream)
                with stream:
                    archived[member.name] = stream.read()
        return archived

    def test_spdx_files_include_required_sha1_and_sha256_checksums(self) -> None:
        sbom = self._build()
        archived = self._archive_bytes()

        for item in sbom["files"]:
            data = archived[item["fileName"]]
            checksums = {
                checksum["algorithm"]: checksum["checksumValue"]
                for checksum in item["checksums"]
            }
            expected_sha1 = hashlib.sha1(
                data, usedforsecurity=False
            ).hexdigest()
            self.assertEqual(checksums["SHA1"], expected_sha1)
            self.assertEqual(
                checksums["SHA256"], hashlib.sha256(data).hexdigest()
            )

    def test_spdx_file_metadata_does_not_claim_an_unscanned_header(
        self,
    ) -> None:
        sbom = self._build()
        self.assertTrue(sbom["files"])
        for item in sbom["files"]:
            self.assertEqual(item["licenseInfoInFiles"], ["NOASSERTION"])
            self.assertEqual(item["copyrightText"], "NOASSERTION")

    def test_spdx_package_verification_code_matches_file_sha1_inventory(
        self,
    ) -> None:
        sbom = self._build()
        archived = self._archive_bytes()
        file_sha1s = [
            hashlib.sha1(
                archived[item["fileName"]], usedforsecurity=False
            ).hexdigest()
            for item in sbom["files"]
        ]

        expected_verification_code = hashlib.sha1(
            "".join(sorted(file_sha1s)).encode("ascii"),
            usedforsecurity=False,
        ).hexdigest()
        package = sbom["packages"][0]
        self.assertEqual(
            package["packageVerificationCode"],
            {"packageVerificationCodeValue": expected_verification_code},
        )

    def test_archive_reader_closes_every_extracted_stream(self) -> None:
        archive_builder = _load("agent_collab_archive_stream_close", ARCHIVE_SCRIPT)
        evidence_builder = _load("agent_collab_evidence_stream_close", EVIDENCE_SCRIPT)
        archive_builder.build_archive(
            ROOT, plugin="agent-collab", output=self.archive
        )
        streams = []
        original_extractfile = tarfile.TarFile.extractfile

        def tracked_extractfile(bundle, member):
            stream = original_extractfile(bundle, member)
            if stream is not None:
                streams.append(stream)
            return stream

        with patch.object(tarfile.TarFile, "extractfile", tracked_extractfile):
            evidence_builder._archive_files(self.archive)

        self.assertTrue(streams)
        self.assertTrue(all(stream.closed for stream in streams))

    def test_failed_exclusive_write_removes_its_partial_output(self) -> None:
        evidence_builder = _load(
            "agent_collab_evidence_partial_cleanup", EVIDENCE_SCRIPT
        )
        with patch.object(
            evidence_builder.os,
            "fsync",
            side_effect=OSError("simulated fsync failure"),
        ):
            with self.assertRaisesRegex(OSError, "simulated fsync failure"):
                evidence_builder._write_exclusive(self.sbom, b"partial")

        self.assertFalse(self.sbom.exists())

    def test_checksum_sidecar_names_and_hashes_archive(self) -> None:
        self._build()
        expected = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.assertEqual(
            self.checksum.read_text(encoding="utf-8"),
            f"{expected}  {self.archive.name}\n",
        )

    def test_release_evidence_outputs_are_owner_only(self) -> None:
        previous_umask = os.umask(0)
        try:
            self._build()
        finally:
            os.umask(previous_umask)
        self.assertEqual(stat.S_IMODE(self.sbom.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.checksum.stat().st_mode), 0o600)

    def test_rejects_non_semver_version_before_writing_outputs(self) -> None:
        self.assertTrue(EVIDENCE_SCRIPT.is_file())
        archive_builder = _load("agent_collab_archive_invalid_version", ARCHIVE_SCRIPT)
        evidence_builder = _load("agent_collab_evidence_invalid_version", EVIDENCE_SCRIPT)
        archive_builder.build_archive(ROOT, plugin="agent-collab", output=self.archive)
        with self.assertRaisesRegex(ValueError, "version"):
            evidence_builder.build_evidence(
                self.archive,
                version="latest",
                created="2026-07-12T00:00:00Z",
                sbom_output=self.sbom,
                checksum_output=self.checksum,
                repo_root=ROOT,
            )
        self.assertFalse(self.sbom.exists())
        self.assertFalse(self.checksum.exists())

    def test_output_path_rejects_an_unresolved_archive_alias(self) -> None:
        evidence_builder = _load(
            "agent_collab_evidence_archive_alias", EVIDENCE_SCRIPT
        )
        missing_archive = self.root / "missing.plugin"
        relative_alias = Path(os.path.relpath(missing_archive, Path.cwd()))

        with self.assertRaisesRegex(ValueError, "aliases the archive"):
            evidence_builder._validate_output_path(
                relative_alias,
                archive=missing_archive,
            )

    def test_rejects_canonically_identical_output_paths_before_writing(
        self,
    ) -> None:
        archive_builder = _load(
            "agent_collab_archive_output_alias", ARCHIVE_SCRIPT
        )
        evidence_builder = _load(
            "agent_collab_evidence_output_alias", EVIDENCE_SCRIPT
        )
        archive_builder.build_archive(
            ROOT, plugin="agent-collab", output=self.archive
        )
        relative_sbom = Path(os.path.relpath(self.sbom, Path.cwd()))

        with self.assertRaisesRegex(ValueError, "different paths"):
            evidence_builder.build_evidence(
                self.archive,
                version=PACKAGE_VERSION,
                created="2026-07-12T00:00:00Z",
                sbom_output=relative_sbom,
                checksum_output=self.sbom,
                repo_root=ROOT,
            )

        self.assertFalse(self.sbom.exists())

    def test_created_timestamp_rejects_lowercase_utc_suffix(self) -> None:
        evidence_builder = _load(
            "agent_collab_evidence_lowercase_utc", EVIDENCE_SCRIPT
        )

        with self.assertRaisesRegex(ValueError, "must use uppercase Z"):
            evidence_builder._normalize_created("2026-07-12T00:00:00z")


if __name__ == "__main__":
    unittest.main()
