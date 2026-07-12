"""Deterministic checksum and SPDX evidence for release archives."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SCRIPT = ROOT / "scripts" / "build_plugin_archive.py"
EVIDENCE_SCRIPT = ROOT / "scripts" / "build_release_evidence.py"
LEGAL_FILES = {"LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md"}


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
        self.archive = self.root / "agent-collab v3.1.0.plugin"
        self.sbom = self.root / "agent-collab-v3.1.0.spdx.json"
        self.checksum = self.root / "agent-collab v3.1.0.plugin.sha256"

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
            version="3.1.0",
            created="2026-07-12T00:00:00Z",
            sbom_output=self.sbom,
            checksum_output=self.checksum,
            repo_root=ROOT,
        )
        return json.loads(self.sbom.read_text(encoding="utf-8"))

    def test_spdx_inventory_contains_exact_legal_files_and_license(self) -> None:
        sbom = self._build()

        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["dataLicense"], "CC0-1.0")
        self.assertEqual(sbom["creationInfo"]["created"], "2026-07-12T00:00:00Z")
        package = sbom["packages"][0]
        self.assertEqual(package["versionInfo"], "3.1.0")
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


if __name__ == "__main__":
    unittest.main()
