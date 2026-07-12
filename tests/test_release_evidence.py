"""Deterministic checksum and SPDX evidence for release archives."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


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

    def test_every_spdx_file_checksum_matches_archive_bytes(self) -> None:
        import tarfile

        sbom = self._build()
        with tarfile.open(self.archive, "r:gz") as bundle:
            archived = {
                member.name: bundle.extractfile(member).read()
                for member in bundle.getmembers()
                if member.isfile()
            }
        for item in sbom["files"]:
            checksum = item["checksums"]
            self.assertEqual(checksum[0]["algorithm"], "SHA256")
            self.assertEqual(
                checksum[0]["checksumValue"],
                hashlib.sha256(archived[item["fileName"]]).hexdigest(),
            )

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
