"""Tests for the public project-estimation maintenance gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "plugins" / "agent-collab" / "project-estimation-data"


def _load_verifier():
    path = ROOT / "scripts" / "verify_project_estimation_maintenance.py"
    spec = importlib.util.spec_from_file_location("project_estimation_maintenance", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_data(root: Path) -> Path:
    destination = root / "plugins" / "agent-collab" / "project-estimation-data"
    destination.mkdir(parents=True)
    for source in DATA.iterdir():
        shutil.copy2(source, destination / source.name)
    return destination


def _receipt(data: Path, *, version: str = "6.2.0", today: date = date(2026, 8, 20)) -> dict[str, object]:
    inventory = sorted(path.name for path in data.iterdir() if path.name != "maintenance-receipt.json")
    hashes = {
        name: hashlib.sha256((data / name).read_bytes()).hexdigest()
        for name in inventory
    }
    receipt = {
        "schema_version": 1,
        "version": version,
        "estimator_method_version": "empirical-v1",
        "generated_date": today.isoformat(),
        "source_cutoff_date": today.isoformat(),
        "policy_version": "2026.08.1",
        "policy_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "inventory": inventory,
        "admitted_sha256": hashes,
        "calibration_outcome": "fresh",
        "pricing_outcome": "official",
        "quota_outcome": "official",
        "pricing_original_last_good_date": today.isoformat(),
        "quota_original_last_good_date": today.isoformat(),
        "operator_notification_required": False,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        (json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    ).hexdigest()
    return receipt


def _write_receipt(data: Path, receipt: dict[str, object]) -> None:
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = hashlib.sha256(
        (json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    ).hexdigest()
    (data / "maintenance-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")


class MaintenanceVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = _load_verifier()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = _copy_data(self.root)
        receipt = _receipt(self.data)
        (self.data / "maintenance-receipt.json").write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_valid_receipt_and_exact_day_60_and_90_pass(self) -> None:
        receipt = _receipt(self.data, today=date(2026, 8, 20))
        receipt["generated_date"] = "2026-06-21"
        receipt["source_cutoff_date"] = "2026-06-21"
        receipt["pricing_original_last_good_date"] = "2026-05-22"
        receipt["quota_original_last_good_date"] = "2026-05-22"
        _write_receipt(self.data, receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version="6.2.0", today=date(2026, 8, 20))
        self.assertTrue(ok, lines)

    def test_day_61_calibration_and_day_91_material_pricing_fail(self) -> None:
        receipt = _receipt(self.data)
        receipt["generated_date"] = "2026-06-20"
        receipt["source_cutoff_date"] = "2026-06-20"
        receipt["pricing_original_last_good_date"] = "2026-05-21"
        receipt["quota_original_last_good_date"] = "2026-05-21"
        receipt["pricing_outcome"] = "estimated_stale"
        _write_receipt(self.data, receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version="6.2.0", today=date(2026, 8, 20))
        self.assertFalse(ok)
        self.assertTrue(any("calibration" in line or "pricing" in line for line in lines), lines)

    def test_wrong_version_hash_and_receipt_declared_file_fail(self) -> None:
        receipt = _receipt(self.data)
        receipt["version"] = "6.1.1"
        receipt["admitted_sha256"]["not-in-inventory.json"] = "c" * 64
        _write_receipt(self.data, receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version="6.2.0", today=date(2026, 8, 20))
        self.assertFalse(ok)
        self.assertTrue(any("version" in line or "inventory" in line for line in lines), lines)

    def test_wrong_schema_fails_closed(self) -> None:
        receipt = _receipt(self.data)
        receipt.pop("schema_version")
        _write_receipt(self.data, receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version="6.2.0", today=date(2026, 8, 20))
        self.assertFalse(ok)
        self.assertTrue(any("schema" in line or "receipt" in line for line in lines), lines)

    def test_extra_raw_evidence_is_not_admitted(self) -> None:
        (self.data / "raw-observations.json").write_text("{}", encoding="utf-8")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version="6.2.0", today=date(2026, 8, 20))
        self.assertFalse(ok)
        self.assertTrue(any("inventory" in line or "raw" in line for line in lines), lines)

    def test_public_member_plan_is_exact_and_non_recursive(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive

        with mock.patch.object(archive, "_safe_source"), \
                mock.patch.object(archive, "_require_no_development_members"), \
                mock.patch.object(archive, "_require_exact_manifest_trees"), \
                mock.patch.object(archive, "skill_tree_differences", return_value=[]), \
                mock.patch.object(archive, "expected_skill_relpaths", return_value=[]):
            plan = archive._member_plan(DATA.parent, mode="policy-only")
        names = {name for name, _ in plan}
        self.assertIn("project-estimation-data/maintenance-receipt.json", names)
        self.assertNotIn("project-estimation-data/raw-observations.json", names)

    def test_release_workflow_runs_verifier_before_archive_and_release(self) -> None:
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        verify = text.index("scripts/verify_project_estimation_maintenance.py")
        archive = text.index("scripts/build_plugin_archive.py", verify)
        release = text.index("gh release create", archive)
        self.assertLess(verify, archive)
        self.assertLess(archive, release)


if __name__ == "__main__":
    unittest.main()
