"""Adversarial tests for the public Task 7 maintenance admission gate."""

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
DATA_SOURCE = ROOT / "plugins" / "agent-collab" / "project-estimation-data"
TODAY = date(2026, 8, 20)
VERSION = "6.1.1"
DIGEST = "a" * 64


def _load_verifier():
    path = ROOT / "scripts" / "verify_project_estimation_maintenance.py"
    spec = importlib.util.spec_from_file_location("project_estimation_maintenance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _node(release_hash: str = DIGEST) -> dict[str, object]:
    return {
        "schema_version": 1, "estimator_method_version": "empirical-v2", "generated_date": "2026-08-20",
        "source_cutoff_date": "2026-08-20", "hierarchy_node": "all", "fallback_parent": None,
        "sample_count": 20, "effective_sample_size": 20, "aggregate_sha256": DIGEST,
        "release_manifest_sha256": release_hash,
        "phase_duration_quantiles": [{"phase": "overall", "p50": 1, "p80": 2, "p95": 3}],
    }


def _aggregate(release_hash: str = DIGEST) -> dict[str, object]:
    return {
        "schema_version": 1, "estimator_method_version": "empirical-v2", "generated_date": "2026-08-20",
        "source_cutoff_date": "2026-08-20", "policy_version": "calibration-v1", "policy_sha256": DIGEST,
        "seed": 1, "source_manifest_sha256": DIGEST, "nodes": [_node(release_hash)],
    }


def _record(kind: str = "pricing") -> dict[str, object]:
    if kind == "pricing":
        value = {"record_id": "r1", "model": "m", "modality": "text", "tier": "standard", "token_class": "input", "currency": "USD", "unit": "token", "amount_microusd": 1, "amount_text": "0.000001", "modifiers": []}
    else:
        value = {"record_id": "r1", "model": "m", "modality": "text", "tier": "standard", "limit_kind": "rpm", "limit_value": 1, "window_seconds": 60, "cooldown_seconds": 0, "modifiers": []}
    value["approved_value_sha256"] = _sha(value)
    return value


def _provider(kind: str, provider: str = "provider-a", status: str = "official") -> dict[str, object]:
    record = _record(kind)
    values = [record] if status in {"official", "estimated_stale"} else []
    return {
        "provider": provider, "status": status, "retrieved_date": "2026-08-20" if status in {"official", "estimated_stale"} else None,
        "last_successful_official_date": "2026-08-20" if status in {"official", "estimated_stale"} else None,
        "original_last_good_date": "2026-08-20" if status == "estimated_stale" else None, "values": values, "value_sha256": _sha(values) if values else None,
        "source_url_sha256": DIGEST if status in {"official", "estimated_stale"} else None, "final_url_sha256": DIGEST if status in {"official", "estimated_stale"} else None,
        "redirect_chain_sha256": DIGEST if status in {"official", "estimated_stale"} else None, "content_type": "text/html" if status in {"official", "estimated_stale"} else None,
        "elapsed_class": "fast" if status in {"official", "estimated_stale"} else None, "failure_class": None if status == "official" else "refresh_failed",
        "material_share_basis_points": 10000,
    }


def _snapshot(kind: str = "pricing", status: str = "official") -> dict[str, object]:
    row = _provider(kind, status=status)
    return {"schema_version": 1, "kind": kind, "policy_version": "policy-v1", "policy_sha256": DIGEST,
            "retrieved_date": "2026-08-20", "providers": {"provider-a": row},
            "operator_notification_required": status != "official", "material_unpriced": False,
            "uncertainty_basis_points": 0 if status == "official" else 1}


def _notification() -> dict[str, object]:
    return {"schema_version": 1, "generated_date": "2026-08-20", "unresolved": [{
        "provider": "provider-a", "kind": "pricing", "original_date": "2026-08-20",
        "failure_class": "refresh_failed", "decision": "estimated_stale",
    }], "pricing_coverage_basis_points": 0, "quota_coverage_basis_points": 10000,
            "decision": "unpriced_block"}


def _receipt(*, notification: bool, generated: str, pricing: dict[str, object], quota: dict[str, object]) -> dict[str, object]:
    files = ["aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json"]
    if notification:
        files.append("operator-notification.json")
    return {
        "schema_version": 2, "version": VERSION, "estimator_method_version": "empirical-v2",
        "calibration_policy_version": "calibration-v1", "calibration_policy_sha256": DIGEST,
        "pricing_policy_version": "policy-v1", "pricing_policy_sha256": DIGEST,
        "pricing_registry_sha256": DIGEST, "quota_registry_sha256": DIGEST,
        "pricing_material_unpriced_threshold_basis_points": 1000, "seed": 1, "repository_sha256": DIGEST,
        "collection_cutoff_date": generated, "collection_result_sha256": DIGEST, "linkage_manifest_sha256": DIGEST,
        "completion_evidence_scope": "github_merged_or_earlier", "source_cutoff_date": generated,
        "generated_date": generated, "calibration_status": "fresh", "original_calibration_date": generated,
        "source_manifest_sha256": DIGEST, "calibration_candidate_sha256": DIGEST,
        "calibration_source_receipt_sha256": None,
        "backtest_outcome": {"promotion_allowed": True, "baseline_duration_comparison": "not_applicable", "baseline_token_comparison": "not_applicable"},
        "pricing_result_sha256": _sha(pricing), "quota_result_sha256": _sha(quota),
        "notification_result": "delivered" if notification else "not_required", "release_manifest_sha256": DIGEST,
        "inventory": files, "receipt_sha256": DIGEST,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode())


def _fixture(root: Path, *, notification: bool = False, generated: str = "2026-08-20") -> Path:
    data = root / "plugins" / "agent-collab" / "project-estimation-data"
    data.mkdir(parents=True)
    for source in DATA_SOURCE.glob("*.schema.json"):
        shutil.copy2(source, data / source.name)
    aggregate = _aggregate()
    pricing = _snapshot("pricing", "estimated_stale" if notification else "official")
    quota = _snapshot("quota")
    _write_json(data / "aggregate-prior.json", aggregate)
    _write_json(data / "pricing-snapshot.json", pricing)
    _write_json(data / "quota-snapshot.json", quota)
    if notification:
        _write_json(data / "operator-notification.json", _notification())
    receipt = _receipt(notification=notification, generated=generated, pricing=pricing, quota=quota)
    receipt["inventory"] = [{"name": name, "sha256": hashlib.sha256((data / name).read_bytes()).hexdigest(), "size": (data / name).stat().st_size} for name in sorted(["aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json"] + (["operator-notification.json"] if notification else []))]
    receipt["release_manifest_sha256"] = _sha({key: value for key, value in receipt.items() if key not in {"release_manifest_sha256", "inventory", "receipt_sha256"}})
    aggregate["nodes"][0]["release_manifest_sha256"] = receipt["release_manifest_sha256"]
    _write_json(data / "aggregate-prior.json", aggregate)
    receipt["inventory"][0]["sha256"] = hashlib.sha256((data / "aggregate-prior.json").read_bytes()).hexdigest()
    receipt["inventory"][0]["size"] = (data / "aggregate-prior.json").stat().st_size
    receipt["receipt_sha256"] = _sha({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(data / "maintenance-receipt.json", receipt)
    return data


def _rebind(data: Path, *, provider_date: str) -> None:
    pricing = json.loads((data / "pricing-snapshot.json").read_text())
    pricing["retrieved_date"] = provider_date
    pricing["providers"]["provider-a"]["retrieved_date"] = provider_date
    pricing["providers"]["provider-a"]["last_successful_official_date"] = provider_date
    _write_json(data / "pricing-snapshot.json", pricing)
    receipt = json.loads((data / "maintenance-receipt.json").read_text())
    receipt["pricing_result_sha256"] = _sha(pricing)
    receipt["release_manifest_sha256"] = _sha({key: value for key, value in receipt.items() if key not in {"release_manifest_sha256", "inventory", "receipt_sha256"}})
    aggregate = json.loads((data / "aggregate-prior.json").read_text())
    for node in aggregate["nodes"]:
        node["release_manifest_sha256"] = receipt["release_manifest_sha256"]
    _write_json(data / "aggregate-prior.json", aggregate)
    for item in receipt["inventory"]:
        payload = data / item["name"]
        item["sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
        item["size"] = payload.stat().st_size
    receipt["receipt_sha256"] = _sha({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(data / "maintenance-receipt.json", receipt)


class MaintenanceVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = _load_verifier()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def check(self, *, notification: bool = False, generated: str = "2026-08-20") -> tuple[bool, list[str]]:
        _fixture(self.root, notification=notification, generated=generated)
        return self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)

    def test_complete_task7_fixture_and_day_60_pass(self) -> None:
        ok, lines = self.check(generated="2026-06-21")
        self.assertTrue(ok, lines)

    def test_day_61_fails_closed(self) -> None:
        _fixture(self.root, generated="2026-06-20")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("60" in line or "calibration" in line for line in lines), lines)

    def test_provider_day_90_passes_and_day_91_fails(self) -> None:
        data = _fixture(self.root)
        _rebind(data, provider_date="2026-05-22")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertTrue(ok, lines)
        _rebind(data, provider_date="2026-05-21")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("stale" in line or "expired" in line or "90" in line for line in lines), lines)

    def test_strict_receipt_and_extra_raw_private_linked_files_fail(self) -> None:
        data = _fixture(self.root)
        receipt = json.loads((data / "maintenance-receipt.json").read_text())
        receipt["unexpected"] = "private"
        _write_json(data / "maintenance-receipt.json", receipt)
        (data / "raw-observations.json").write_text("{}")
        (data / "private-secret.json").symlink_to(data / "aggregate-prior.json")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("inventory" in line or "unknown" in line or "symlink" in line or "forbidden" in line for line in lines), lines)

    def test_quantile_duplicate_and_nonfinite_are_rejected(self) -> None:
        data = _fixture(self.root)
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        aggregate["nodes"][0]["phase_duration_quantiles"].append({"phase": "overall", "p50": 1, "p80": 2, "p95": 3})
        _write_json(data / "aggregate-prior.json", aggregate)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("aggregate" in line or "quant" in line for line in lines), lines)
        (data / "pricing-snapshot.json").write_bytes(b'{"schema_version":1,"kind":"pricing","retrieved_date":NaN}')
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("finite" in line or "JSON" in line for line in lines), lines)

    def test_conditional_notification_is_required_and_validated(self) -> None:
        data = _fixture(self.root, notification=True)
        (data / "operator-notification.json").unlink()
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("notification" in line for line in lines), lines)

    def test_descriptor_relative_root_rejects_final_symlink(self) -> None:
        data = _fixture(self.root)
        real = data.parent / "real-data"
        data.rename(real)
        data.symlink_to(real, target_is_directory=True)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("symlink" in line or "root" in line for line in lines), lines)

    def test_archive_plan_is_closed_and_contains_actual_data_members(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        with mock.patch.object(archive, "_safe_source"), mock.patch.object(archive, "_require_no_development_members"), mock.patch.object(archive, "_require_exact_manifest_trees"), mock.patch.object(archive, "skill_tree_differences", return_value=[]), mock.patch.object(archive, "expected_skill_relpaths", return_value=[]):
            plan = archive._member_plan(DATA_SOURCE.parent, mode="policy-only")
        names = {str(name) for name, _ in plan}
        for name in ("aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json", "maintenance-receipt.json", "operator-notification.schema.json"):
            self.assertIn(f"project-estimation-data/{name}", names)
        self.assertNotIn("project-estimation-data/raw-observations.json", names)


if __name__ == "__main__":
    unittest.main()
