"""Adversarial tests for the public Task 7 maintenance admission gate."""

from __future__ import annotations

import hashlib
import io
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
DATA_SOURCE = ROOT / "plugins" / "agent-collab" / "project-estimation-data"
TODAY = date(2026, 8, 20)
VERSION = "6.2.0"
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
        "schema_version": 1, "estimator_method_version": "empirical-v3", "generated_date": "2026-08-20",
        "source_cutoff_date": "2026-08-20", "hierarchy_node": "project_type.enhancement", "fallback_parent": None,
        "sample_count": 20, "effective_sample_size": 20, "aggregate_sha256": DIGEST,
        "release_manifest_sha256": release_hash,
        "metric_support": {
            "actual_marginal_cash": {"status": "unavailable", "eligible_count": 0},
            "focused_duration": {"status": "published", "eligible_count": 20},
            "quota_delay": {"status": "unavailable", "eligible_count": 0},
            "rework_review": {"status": "unavailable", "eligible_count": 0},
            "token_usage": {"status": "unavailable", "eligible_count": 0},
            "wait_class": {"status": "unavailable", "eligible_count": 0},
        },
        "phase_duration_quantiles": [{"phase": "overall", "p50": 1, "p80": 2, "p95": 3}],
    }


def _aggregate(release_hash: str = DIGEST) -> dict[str, object]:
    return {
        "schema_version": 2, "estimator_method_version": "empirical-v3", "generated_date": "2026-08-20",
        "source_cutoff_date": "2026-08-20", "policy_version": "calibration-v1", "policy_sha256": DIGEST,
        "seed": 1, "source_manifest_sha256": DIGEST, "calibration_state": "bootstrap",
        "excluded_observation_count_floor": 0, "exclusion_count_rounding": "floor_to_public_k",
        "limitations": ["bootstrap_descriptive_only"], "nodes": [_node(release_hash)],
    }


def _record(kind: str = "pricing") -> dict[str, object]:
    if kind == "pricing":
        value = {"record_id": "r1", "model": "m", "modality": "text", "tier": "standard", "token_class": "input", "currency": "USD", "unit": "per_million_tokens", "amount_microusd": 1, "amount_text": "0.000001", "modifiers": []}
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
    }], "pricing_coverage_basis_points": 10000, "quota_coverage_basis_points": 10000,
            "decision": "stale_fallback"}


def _receipt(*, notification: bool, generated: str, pricing: dict[str, object], quota: dict[str, object]) -> dict[str, object]:
    files = ["aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json"]
    if notification:
        files.append("operator-notification.json")
    return {
        "schema_version": 3, "version": VERSION, "estimator_method_version": "empirical-v3",
        "calibration_policy_version": "calibration-v1", "calibration_policy_sha256": DIGEST,
        "pricing_policy_version": "policy-v1", "pricing_policy_sha256": DIGEST,
        "pricing_registry_sha256": DIGEST, "quota_registry_sha256": DIGEST,
        "pricing_material_unpriced_threshold_basis_points": 1000, "seed": 1, "repository_sha256": DIGEST,
        "collection_cutoff_date": generated, "collection_result_sha256": DIGEST, "linkage_manifest_sha256": DIGEST,
        "completion_evidence_scope": "github_merged_or_earlier", "source_cutoff_date": generated,
        "generated_date": generated, "calibration_status": "fresh", "original_calibration_date": generated,
        "source_manifest_sha256": DIGEST, "calibration_candidate_sha256": DIGEST,
        "calibration_source_receipt_sha256": None, "calibration_state": "bootstrap",
        "calibration_baseline_receipt_sha256": None,
        "backtest_outcome": {"evaluation_mode": "informational", "policy_result": "not_required", "baseline_duration_comparison": "not_applicable", "baseline_token_comparison": "not_applicable", "warning_codes": []},
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
    aggregate["generated_date"] = generated
    aggregate["source_cutoff_date"] = generated
    aggregate["nodes"][0]["generated_date"] = generated
    aggregate["nodes"][0]["source_cutoff_date"] = generated
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


def _rebind_receipt(data: Path) -> None:
    receipt = json.loads((data / "maintenance-receipt.json").read_text())
    for kind in ("pricing", "quota"):
        snapshot = json.loads((data / f"{kind}-snapshot.json").read_text())
        receipt[f"{kind}_result_sha256"] = _sha(snapshot)
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


def _chronology_fixture(data: Path, *, collection: str, source: str, original: str, generated: str) -> None:
    receipt = json.loads((data / "maintenance-receipt.json").read_text())
    receipt.update({"collection_cutoff_date": collection, "source_cutoff_date": source, "original_calibration_date": original, "generated_date": generated})
    if generated != original:
        receipt["calibration_status"] = "last_good"
        receipt["calibration_source_receipt_sha256"] = DIGEST
    aggregate = json.loads((data / "aggregate-prior.json").read_text())
    aggregate.update({"generated_date": original, "source_cutoff_date": source})
    for node in aggregate["nodes"]:
        node.update({"generated_date": original, "source_cutoff_date": source})
    _write_json(data / "aggregate-prior.json", aggregate)
    _write_json(data / "maintenance-receipt.json", receipt)
    _rebind_receipt(data)


class MaintenanceVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = _load_verifier()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def check(self, *, notification: bool = False, generated: str = "2026-08-20") -> tuple[bool, list[str]]:
        _fixture(self.root, notification=notification, generated=generated)
        return self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)

    def test_complete_task7_fixture_and_day_60_pass(self) -> None:
        ok, lines = self.check(generated="2026-06-21")
        self.assertTrue(ok, lines)

    def test_shared_public_semantic_validators_are_each_called_once(self) -> None:
        _fixture(self.root)
        with (
            mock.patch.object(self.verifier._PUBLIC_ESTIMATOR, "validate_aggregate", wraps=self.verifier._PUBLIC_ESTIMATOR.validate_aggregate) as aggregate,
            mock.patch.object(self.verifier._PUBLIC_ESTIMATOR, "validate_pricing", wraps=self.verifier._PUBLIC_ESTIMATOR.validate_pricing) as pricing,
            mock.patch.object(self.verifier._PUBLIC_ESTIMATOR, "validate_quota", wraps=self.verifier._PUBLIC_ESTIMATOR.validate_quota) as quota,
        ):
            ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertTrue(ok, lines)
        aggregate.assert_called_once()
        pricing.assert_called_once()
        quota.assert_called_once()

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

    def test_aggregate_identity_bindings_and_release_manifest_digest_are_verified(self) -> None:
        data = _fixture(self.root)
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        aggregate["policy_version"] = "forged-policy"
        _write_json(data / "aggregate-prior.json", aggregate)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("aggregate" in line or "identity" in line for line in lines), lines)

        shutil.rmtree(self.root / "plugins")
        data = _fixture(self.root)
        receipt = json.loads((data / "maintenance-receipt.json").read_text())
        forged = "f" * 64
        receipt["release_manifest_sha256"] = forged
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        for node in aggregate["nodes"]:
            node["release_manifest_sha256"] = forged
        _write_json(data / "aggregate-prior.json", aggregate)
        receipt["receipt_sha256"] = _sha({key: value for key, value in receipt.items() if key != "receipt_sha256"})
        _write_json(data / "maintenance-receipt.json", receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("release" in line or "receipt" in line for line in lines), lines)

    def test_task3_chronology_allows_independent_collection_source_order(self) -> None:
        data = _fixture(self.root, generated="2026-08-20")
        _chronology_fixture(data, collection="2026-08-19", source="2026-08-18", original="2026-08-20", generated="2026-08-20")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertTrue(ok, lines)

    def test_task3_chronology_rejects_cutoffs_after_original_calibration(self) -> None:
        data = _fixture(self.root, generated="2026-08-25")
        _chronology_fixture(data, collection="2026-08-21", source="2026-08-21", original="2026-08-20", generated="2026-08-25")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=date(2026, 8, 25))
        self.assertFalse(ok)
        self.assertTrue(any("chronology" in line or "date" in line for line in lines), lines)

    def test_snapshot_policy_identity_and_notification_coverage_are_bound(self) -> None:
        data = _fixture(self.root, notification=True)
        pricing = json.loads((data / "pricing-snapshot.json").read_text())
        pricing["policy_version"] = "forged-policy"
        _write_json(data / "pricing-snapshot.json", pricing)
        _rebind_receipt(data)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("policy" in line for line in lines), lines)

        shutil.rmtree(self.root / "plugins")
        data = _fixture(self.root, notification=True)
        notice = json.loads((data / "operator-notification.json").read_text())
        notice["pricing_coverage_basis_points"] = 0
        _write_json(data / "operator-notification.json", notice)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("notification" in line or "coverage" in line for line in lines), lines)

    def test_bad_version_rebound_fixtures_are_rejected_by_runtime_and_schema(self) -> None:
        cases = (
            ("aggregate", "aggregate-prior.json", "policy_version", "calibration_policy_version", "aggregate-prior.schema.json"),
            ("pricing", "pricing-snapshot.json", "policy_version", "pricing_policy_version", "pricing-snapshot.schema.json"),
            ("quota", "quota-snapshot.json", "policy_version", "pricing_policy_version", "quota-snapshot.schema.json"),
        )
        for kind, filename, document_field, receipt_field, schema_name in cases:
            with self.subTest(kind=kind):
                shutil.rmtree(self.root / "plugins", ignore_errors=True)
                data = _fixture(self.root)
                document = json.loads((data / filename).read_text())
                document[document_field] = "bad version"
                _write_json(data / filename, document)
                receipt = json.loads((data / "maintenance-receipt.json").read_text())
                receipt[receipt_field] = "bad version"
                if kind == "aggregate":
                    receipt["calibration_policy_sha256"] = DIGEST
                _write_json(data / "maintenance-receipt.json", receipt)
                _rebind_receipt(data)
                ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
                self.assertFalse(ok, lines)
                schema = json.loads((DATA_SOURCE / schema_name).read_text())
                self.assertIsNone(re.fullmatch(schema["$defs"]["version"]["pattern"], "bad version"))
                shutil.rmtree(self.root / "plugins")

    def test_snapshot_date_schema_and_runtime_use_strict_gregorian_pattern(self) -> None:
        for schema_name in ("pricing-snapshot.schema.json", "quota-snapshot.schema.json"):
            schema = json.loads((DATA_SOURCE / schema_name).read_text())
            date_schema = schema["$defs"]["date"]
            self.assertEqual(date_schema.get("pattern"), rf"^{self.verifier._DATE_PATTERN}$")
            self.assertNotIn("format", date_schema)
        for value in ("2026-02-29", "2026-13-01", "2026-04-31"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.verifier._date(value, field="date")

    def test_fifo_members_are_rejected_without_blocking(self) -> None:
        data = _fixture(self.root)
        os.unlink(data / "pricing-snapshot.json")
        os.mkfifo(data / "pricing-snapshot.json")
        command = [sys.executable, str(ROOT / "scripts" / "verify_project_estimation_maintenance.py"), "--root", str(self.root), "--expected-version", VERSION]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=2)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("regular", completed.stdout + completed.stderr)

    def test_caller_visible_intermediate_parent_symlink_is_rejected(self) -> None:
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        source = _fixture(real_parent / "child")
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        ok, lines = self.verifier.verify_maintenance(linked_parent / "child", expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("root" in line or "symlink" in line for line in lines), lines)

    def test_executable_public_member_is_rejected_by_source_mode_floor(self) -> None:
        data = _fixture(self.root)
        # This deliberately unsafe fixture proves the verifier rejects executable public data.
        # codeql[py/overly-permissive-file]
        (data / "pricing-snapshot.json").chmod(0o755)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("mode" in line or "regular" in line for line in lines), lines)

    def test_world_writable_public_member_is_rejected(self) -> None:
        data = _fixture(self.root)
        # This deliberately unsafe fixture proves the verifier rejects world-writable data.
        # codeql[py/overly-permissive-file]
        (data / "pricing-snapshot.json").chmod(0o666)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("mode" in line or "writable" in line for line in lines), lines)

    def test_foreign_owner_is_rejected_at_descriptor_admission(self) -> None:
        _fixture(self.root)
        with mock.patch.object(self.verifier.os, "getuid", return_value=os.getuid() + 1):
            ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("owner" in line or "current user" in line for line in lines), lines)

    def test_metadata_identity_drift_is_rejected(self) -> None:
        data = _fixture(self.root)
        calls = [0]
        original_identity = self.verifier._identity

        def identity_with_drift(info: os.stat_result):
            calls[0] += 1
            identity = original_identity(info)
            if calls[0] == 2:
                return self.verifier._ReadIdentity(identity.dev, identity.ino, identity.mode, identity.uid, identity.gid, identity.nlink, identity.size, identity.mtime_ns + 1, identity.ctime_ns)
            return identity

        with mock.patch.object(self.verifier, "_identity", side_effect=identity_with_drift):
            ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("changed" in line or "identity" in line for line in lines), lines)

    def test_group_writable_0664_public_member_is_admitted(self) -> None:
        data = _fixture(self.root)
        # This fixture intentionally exercises the verifier's documented group-write allowance.
        # codeql[py/overly-permissive-file]
        (data / "pricing-snapshot.json").chmod(0o664)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertTrue(ok, lines)

    def test_hard_linked_public_member_is_rejected(self) -> None:
        data = _fixture(self.root)
        external = self.root / "pricing-snapshot-copy.json"
        external.write_bytes((data / "pricing-snapshot.json").read_bytes())
        (data / "pricing-snapshot.json").unlink()
        os.link(external, data / "pricing-snapshot.json")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("link" in line or "identity" in line for line in lines), lines)

    def test_notification_date_must_match_receipt_run(self) -> None:
        data = _fixture(self.root, notification=True)
        notification = json.loads((data / "operator-notification.json").read_text())
        notification["generated_date"] = "2026-08-19"
        _write_json(data / "operator-notification.json", notification)
        _rebind_receipt(data)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("notification" in line or "generated" in line for line in lines), lines)

    def test_malformed_optional_prior_family_is_rejected(self) -> None:
        data = _fixture(self.root)
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        aggregate["nodes"][0]["calibration_quality"] = "forged"
        _write_json(data / "aggregate-prior.json", aggregate)
        _rebind_receipt(data)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("calibration" in line or "aggregate" in line for line in lines), lines)

    def test_category_confused_quantile_family_is_rejected(self) -> None:
        data = _fixture(self.root)
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        aggregate["nodes"][0]["token_class_quantiles"] = [{"phase": "overall", "p50": 1, "p80": 2, "p95": 3}]
        _write_json(data / "aggregate-prior.json", aggregate)
        _rebind_receipt(data)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("quant" in line or "token" in line or "aggregate" in line for line in lines), lines)

    def test_all_public_prior_optional_families_have_strict_runtime_shapes(self) -> None:
        data = _fixture(self.root)
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        node = aggregate["nodes"][0]
        node.update({
            "source_eras": ["era-1"],
            "calibration_quality": {"holdout_count": 20, "p80_coverage_basis_points": 8000, "p95_coverage_basis_points": 9500},
            "drift_indicators": {"duration_drift_basis_points": 1, "token_drift_basis_points": 2},
            "uncertainty_floors": {"duration_basis_points": 3, "token_basis_points": 4},
            "pricing_snapshot": {"sha256": DIGEST, "retrieved_date": "2026-08-20", "status": "official"},
        })
        _write_json(data / "aggregate-prior.json", aggregate)
        _rebind_receipt(data)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertTrue(ok, lines)

    def test_each_public_prior_optional_family_rejects_malformed_values(self) -> None:
        malformed = {
            "source_eras": "era-1",
            "calibration_quality": {"holdout_count": "20"},
            "drift_indicators": [],
            "uncertainty_floors": {"duration_basis_points": True},
            "pricing_snapshot": {"sha256": DIGEST, "retrieved_date": "2026-08-20", "status": "bogus"},
        }
        for field, value in malformed.items():
            with self.subTest(field=field):
                shutil.rmtree(self.root / "plugins", ignore_errors=True)
                data = _fixture(self.root)
                aggregate = json.loads((data / "aggregate-prior.json").read_text())
                aggregate["nodes"][0][field] = value
                _write_json(data / "aggregate-prior.json", aggregate)
                _rebind_receipt(data)
                ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
                self.assertFalse(ok, lines)

    def test_optional_arrays_require_exact_list_values(self) -> None:
        class ListSubclass(list):
            pass

        with self.assertRaisesRegex(ValueError, "bounded array"):
            aggregate = _aggregate()
            aggregate["nodes"][0]["phase_duration_quantiles"] = ListSubclass(
                [{"phase": "overall", "p50": 1, "p80": 2, "p95": 3}]
            )
            self.verifier._PUBLIC_ESTIMATOR.validate_aggregate(aggregate)
        with self.assertRaisesRegex(ValueError, "source_eras"):
            aggregate = _aggregate()
            aggregate["nodes"][0]["source_eras"] = ListSubclass(["era-1"])
            self.verifier._PUBLIC_ESTIMATOR.validate_aggregate(aggregate)

    def test_public_prior_schema_matches_task1_identifier_date_and_metric_bounds(self) -> None:
        schema = json.loads((DATA_SOURCE / "aggregate-prior.schema.json").read_text())
        defs = schema["$defs"]
        self.assertEqual(defs["token_quantile"]["properties"]["token_class"]["pattern"], self.verifier._IDENTIFIER_RE.pattern)
        self.assertEqual(defs["wait_quantile"]["properties"]["wait_class"]["pattern"], self.verifier._IDENTIFIER_RE.pattern)
        self.assertEqual(defs["node"]["properties"]["hierarchy_node"]["pattern"], self.verifier._NODE_RE.pattern)
        self.assertEqual(defs["date"]["pattern"], rf"^{self.verifier._DATE_PATTERN}$")
        self.assertEqual(
            defs["phase_quantile"]["properties"]["phase"]["enum"],
            ["overall", "primary", "delegation", "review", "test", "release", "deployment", "rework"],
        )
        self.assertEqual(defs["calibration_quality"]["properties"]["p80_coverage_basis_points"]["maximum"], 1_000_000_000)
        self.assertEqual(defs["uncertainty_floors"]["properties"]["token_basis_points"]["maximum"], 1_000_000_000)

    def test_threshold_zero_is_rejected_by_schema_and_runtime(self) -> None:
        data = _fixture(self.root)
        receipt = json.loads((data / "maintenance-receipt.json").read_text())
        receipt["pricing_material_unpriced_threshold_basis_points"] = 0
        _write_json(data / "maintenance-receipt.json", receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        schema = json.loads((DATA_SOURCE / "maintenance-receipt.schema.json").read_text())
        threshold = schema["properties"]["pricing_material_unpriced_threshold_basis_points"]
        self.assertEqual(threshold["minimum"], 1)

    def test_generated_data_must_use_canonical_bytes(self) -> None:
        data = _fixture(self.root)
        with (data / "aggregate-prior.json").open("ab") as stream:
            stream.write(b"\n")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("canonical" in line or "aggregate" in line for line in lines), lines)

    def test_quota_subscription_windows_and_cooldown_are_strict(self) -> None:
        with self.assertRaises(ValueError):
            quota = _snapshot("quota")
            quota["providers"]["provider-a"]["values"][0].update(
                {"limit_kind": "subscription_5_hour", "window_seconds": 60}
            )
            self.verifier._PUBLIC_ESTIMATOR.validate_quota(quota)

    def test_quota_unpriced_remains_release_blocked_after_shared_validation(self) -> None:
        quota = _snapshot("quota", status="unpriced")
        self.assertEqual(self.verifier._PUBLIC_ESTIMATOR.validate_quota(quota)["kind"], "quota")
        with self.assertRaisesRegex(ValueError, "quota unresolved status"):
            self.verifier._snapshot(quota, kind="quota", today=TODAY, threshold=1000)

    def test_task5_public_schemas_have_nonempty_closed_request_and_result_shapes(self) -> None:
        request = json.loads((DATA_SOURCE / "estimate-request.schema.json").read_text())
        result = json.loads((DATA_SOURCE / "estimate-result.schema.json").read_text())
        self.assertTrue({"as_of_date", "artifact_kind", "invocation_source", "artifact_scope_hash", "auto_invocation_depth", "project_maturity", "phases", "dependency_edges", "routes"} <= set(request["properties"]))
        self.assertTrue({"headline", "detail", "labels", "estimate_unavailable"} <= set(result["properties"]))
        self.assertFalse(request["additionalProperties"])
        self.assertFalse(result["additionalProperties"])

    def test_long_acyclic_fallback_chain_is_admitted(self) -> None:
        data = _fixture(self.root)
        aggregate = json.loads((data / "aggregate-prior.json").read_text())
        nodes = []
        for index in range(1200):
            node = _node()
            node["hierarchy_node"] = "project_type.enhancement" if index == 0 else f"z{index:04d}"
            node["fallback_parent"] = None if index == 0 else ("project_type.enhancement" if index == 1 else f"z{index - 1:04d}")
            node["generated_date"] = aggregate["generated_date"]
            node["source_cutoff_date"] = aggregate["source_cutoff_date"]
            nodes.append(node)
        aggregate["nodes"] = nodes
        _write_json(data / "aggregate-prior.json", aggregate)
        _rebind_receipt(data)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertTrue(ok, lines)

    def test_unknown_receipt_field_is_rejected(self) -> None:
        data = _fixture(self.root)
        receipt = json.loads((data / "maintenance-receipt.json").read_text())
        receipt["unexpected"] = "private"
        _write_json(data / "maintenance-receipt.json", receipt)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("unknown" in line or "receipt" in line for line in lines), lines)

    def test_extra_raw_private_members_are_rejected(self) -> None:
        data = _fixture(self.root)
        (data / "raw-observations.json").write_text("{}")
        (data / "private-secret.json").write_text("secret")
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("inventory" in line or "forbidden" in line for line in lines), lines)

    def test_expected_public_member_symlink_is_rejected(self) -> None:
        data = _fixture(self.root)
        target = data / "pricing-snapshot.json"
        replacement = self.root / "pricing-snapshot-copy.json"
        replacement.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(replacement)
        ok, lines = self.verifier.verify_maintenance(self.root, expected_version=VERSION, today=TODAY)
        self.assertFalse(ok)
        self.assertTrue(any("open" in line or "symlink" in line or "public member" in line for line in lines), lines)

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
        maintenance = archive.MaintenanceSnapshot(
            tuple(archive.FrozenMaintenanceMember(
                archive_name=f"project-estimation-data/{path.name}", payload=b"{}", sha256=hashlib.sha256(b"{}").hexdigest(),
                source_mode=0o644, source_uid=os.getuid(), source_gid=os.getgid(),
            ) for path in sorted(archive.PUBLIC_ESTIMATION_MEMBERS) if path.name != "operator-notification.json"),
            False, TODAY,
        )
        with mock.patch.object(archive, "_safe_source"), mock.patch.object(archive, "_require_no_development_members"), mock.patch.object(archive, "_require_exact_manifest_trees"), mock.patch.object(archive, "skill_tree_differences", return_value=[]), mock.patch.object(archive, "expected_skill_relpaths", return_value=[]):
            plan = archive._member_plan(DATA_SOURCE.parent, mode="policy-only", maintenance=maintenance)
        names = {str(name) for name, _ in plan}
        for name in ("aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json", "maintenance-receipt.json", "operator-notification.schema.json"):
            self.assertIn(f"project-estimation-data/{name}", names)
        self.assertNotIn("project-estimation-data/raw-observations.json", names)

    def test_archive_emission_uses_frozen_maintenance_payload(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        member = archive.FrozenMaintenanceMember(
            archive_name="project-estimation-data/aggregate-prior.json", payload=b"frozen-evidence",
            sha256=hashlib.sha256(b"frozen-evidence").hexdigest(), source_mode=0o644,
            source_uid=os.getuid(), source_gid=os.getgid(),
        )
        tar_bytes, _ = archive._emit_canonical_tar(
            [(member.archive_name, member)], plugin_path=self.root,
            frozen_manifest=None, record_by_name={}, runtime_payloads={}, runtime_dir_modes={},
        )
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
            self.assertEqual(tar.extractfile(member.archive_name).read(), b"frozen-evidence")

    def test_supplied_maintenance_snapshot_rejects_duplicate_missing_and_forged_members(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        _fixture(self.root)
        maintenance = archive.admit_maintenance(self.root, expected_version=VERSION, today=TODAY)
        member = maintenance.members[0]
        bad_snapshots = (
            archive.MaintenanceSnapshot(maintenance.members + (member,), maintenance.notification_required, maintenance.receipt_generated_date),
            archive.MaintenanceSnapshot(maintenance.members[1:], maintenance.notification_required, maintenance.receipt_generated_date),
            archive.MaintenanceSnapshot((archive.FrozenMaintenanceMember(member.archive_name, b"forged", member.sha256, member.source_mode, member.source_uid, member.source_gid), *maintenance.members[1:]), maintenance.notification_required, maintenance.receipt_generated_date),
        )
        for bad in bad_snapshots:
            with self.subTest(snapshot=bad):
                with self.assertRaisesRegex(ValueError, "snapshot|digest|duplicate|missing"):
                    archive._member_plan(DATA_SOURCE.parent, mode="policy-only", maintenance=bad)

    def test_supplied_maintenance_snapshot_rejects_frozen_field_type_drift(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        _fixture(self.root)
        maintenance = archive.admit_maintenance(self.root, expected_version=VERSION, today=TODAY)
        for bad in (
            archive.MaintenanceSnapshot(maintenance.members, 1, maintenance.receipt_generated_date),
            archive.MaintenanceSnapshot(maintenance.members, maintenance.notification_required, "2026-08-20"),
        ):
            with self.subTest(snapshot=bad):
                with self.assertRaisesRegex(ValueError, "snapshot|notification|date"):
                    archive._member_plan(DATA_SOURCE.parent, mode="policy-only", maintenance=bad)

    def test_private_snapshot_validation_rejects_oversize_unsafe_and_duck_typed_members(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        _fixture(self.root)
        maintenance = archive.admit_maintenance(self.root, expected_version=VERSION, today=TODAY)
        member = maintenance.members[0]

        class MemberSubclass(archive.FrozenMaintenanceMember):
            pass

        class SnapshotDuck:
            members = maintenance.members
            notification_required = maintenance.notification_required
            receipt_generated_date = maintenance.receipt_generated_date

        valid_digest = hashlib.sha256(b"x").hexdigest()
        bad_snapshots = (
            archive.MaintenanceSnapshot(
                tuple(archive.FrozenMaintenanceMember(
                    item.archive_name,
                    b"x" * 1_048_577 if item is member else item.payload,
                    valid_digest if item is member else item.sha256,
                    item.source_mode, item.source_uid, item.source_gid,
                ) for item in maintenance.members),
                maintenance.notification_required, maintenance.receipt_generated_date,
            ),
            archive.MaintenanceSnapshot(
                tuple(archive.FrozenMaintenanceMember(
                    item.archive_name, item.payload, item.sha256,
                    0o777 if item is member else item.source_mode,
                    item.source_uid + 1 if item is member else item.source_uid,
                    "gid" if item is member else item.source_gid,
                ) for item in maintenance.members),
                maintenance.notification_required, maintenance.receipt_generated_date,
            ),
            archive.MaintenanceSnapshot(
                [*maintenance.members], maintenance.notification_required, maintenance.receipt_generated_date,
            ),
            SnapshotDuck(),
            archive.MaintenanceSnapshot(
                (MemberSubclass(member.archive_name, member.payload, member.sha256, member.source_mode, member.source_uid, member.source_gid), *maintenance.members[1:]),
                maintenance.notification_required, maintenance.receipt_generated_date,
            ),
        )
        for bad in bad_snapshots:
            with self.subTest(snapshot_type=type(bad).__name__):
                with self.assertRaisesRegex(ValueError, "snapshot|member|bytes|size|mode|owner|GID|tuple|type"):
                    archive._member_plan(DATA_SOURCE.parent, mode="policy-only", maintenance=bad)

    def test_public_verify_archive_rejects_maintenance_injection_keyword(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        self.assertNotIn("maintenance", inspect.signature(archive.verify_archive).parameters)

    def test_public_verify_archive_freshly_admits_checked_out_tree(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        repo = self.root / "fresh-admission"
        plugin = repo / "plugins" / "agent-collab"
        shutil.copytree(ROOT / "plugins" / "agent-collab", plugin)
        shutil.rmtree(plugin / "project-estimation-data")
        _fixture(repo)
        original_admit = archive.admit_maintenance
        calls: list[object] = []

        def admit_fresh(*args: object, **kwargs: object):
            calls.append(args[0])
            return original_admit(*args, **kwargs)

        with mock.patch.object(archive, "admit_maintenance", side_effect=admit_fresh):
            with self.assertRaises(ValueError):
                archive.verify_archive(plugin, repo / "missing.tgz", mode="policy-only")
        self.assertEqual(calls, [repo])

    def test_direct_archive_rejects_unadmitted_estimation_evidence(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        cases = ("malformed", "wrong-version", "stale", "hash-mismatch", "notification-optional")
        original_admit = archive.admit_maintenance
        for case in cases:
            with self.subTest(case=case):
                repo = self.root / case
                plugin = repo / "plugins" / "agent-collab"
                shutil.copytree(ROOT / "plugins" / "agent-collab", plugin)
                shutil.rmtree(repo / "plugins" / "agent-collab" / "project-estimation-data")
                data = _fixture(repo, notification=case == "notification-optional", generated="2026-06-20" if case == "stale" else "2026-08-20")
                if case == "malformed":
                    receipt = json.loads((data / "maintenance-receipt.json").read_text()); receipt["unexpected"] = "x"; _write_json(data / "maintenance-receipt.json", receipt)
                elif case == "wrong-version":
                    receipt = json.loads((data / "maintenance-receipt.json").read_text()); receipt["version"] = "5.0.0"; _write_json(data / "maintenance-receipt.json", receipt)
                elif case == "hash-mismatch":
                    pricing = json.loads((data / "pricing-snapshot.json").read_text()); pricing["policy_version"] = "forged"; _write_json(data / "pricing-snapshot.json", pricing)
                elif case == "notification-optional":
                    receipt = json.loads((data / "maintenance-receipt.json").read_text()); receipt["notification_result"] = "not_required"; _write_json(data / "maintenance-receipt.json", receipt)
                calls: list[object] = []

                def admit_today(*args: object, **kwargs: object):
                    kwargs["today"] = TODAY
                    calls.append(kwargs["today"])
                    return original_admit(*args, **kwargs)

                with mock.patch.object(archive, "admit_maintenance", side_effect=admit_today):
                    with self.assertRaises(ValueError):
                        archive.build_archive(repo, plugin="agent-collab", output=repo / "archive.tgz")
                self.assertEqual(calls, [TODAY])

    def test_direct_archive_emits_bytes_frozen_before_source_mutation(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_plugin_archive as archive
        repo = self.root / "mutation"
        plugin = repo / "plugins" / "agent-collab"
        shutil.copytree(ROOT / "plugins" / "agent-collab", plugin)
        shutil.rmtree(repo / "plugins" / "agent-collab" / "project-estimation-data")
        data = _fixture(repo)
        expected = (data / "aggregate-prior.json").read_bytes()
        original_admit = archive.admit_maintenance
        calls: list[object] = []

        def admit_and_mutate(*args: object, **kwargs: object):
            kwargs["today"] = TODAY
            snapshot = original_admit(*args, **kwargs)
            calls.append(kwargs["today"])
            (data / "aggregate-prior.json").write_bytes(b"mutated-after-admission")
            return snapshot

        with mock.patch.object(archive, "admit_maintenance", side_effect=admit_and_mutate), mock.patch.object(archive, "verify_archive", side_effect=AssertionError("build must use private same-snapshot verification")):
            archive.build_archive(repo, plugin="agent-collab", output=repo / "archive.tgz")
        self.assertTrue(calls)
        self.assertEqual(calls, [TODAY])
        with tarfile.open(repo / "archive.tgz", mode="r:gz") as tar:
            self.assertEqual(tar.extractfile("project-estimation-data/aggregate-prior.json").read(), expected)


if __name__ == "__main__":
    unittest.main()
