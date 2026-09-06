"""Producer-byte compatibility and staged-bootstrap consumer regressions."""

from __future__ import annotations

import copy
from datetime import date
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from unittest import mock
import shutil
import sys
import tarfile
import tempfile
import unittest

from tests.test_protocol5_public_contract import synthetic_candidate_manifest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
DATA = PLUGIN / "project-estimation-data"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "project_estimation" / "producer"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
CANONICAL = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _documents(kind: str) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    source = FIXTURE_ROOT / kind
    return tuple(json.loads((source / name).read_text(encoding="utf-8")) for name in (
        "aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json",
    ))


def _stage(root: Path, kind: str) -> Path:
    target = root / "plugins" / "agent-collab" / "project-estimation-data"
    target.mkdir(parents=True)
    for schema in DATA.glob("*.schema.json"):
        shutil.copy2(schema, target / schema.name)
    for source in (FIXTURE_ROOT / kind).iterdir():
        shutil.copy2(source, target / source.name)
    return target


def _rebind_receipt(target: Path) -> None:
    receipt_path = target / "maintenance-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["release_manifest_sha256"] = hashlib.sha256(CANONICAL({
        key: value for key, value in receipt.items()
        if key not in {"release_manifest_sha256", "inventory", "receipt_sha256"}
    })).hexdigest()
    aggregate_path = target / "aggregate-prior.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    for node in aggregate["nodes"]:
        node["release_manifest_sha256"] = receipt["release_manifest_sha256"]
    aggregate_path.write_bytes(CANONICAL(aggregate))
    for row in receipt["inventory"]:
        payload = target / row["name"]
        row["sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
        row["size"] = payload.stat().st_size
    receipt["receipt_sha256"] = hashlib.sha256(CANONICAL({
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    })).hexdigest()
    receipt_path.write_bytes(CANONICAL(receipt))


class ProducerByteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.estimator = _load("bootstrap_estimator", PLUGIN / "project_estimation.py")
        cls.verifier = _load("bootstrap_verifier", ROOT / "scripts" / "verify_project_estimation_maintenance.py")
        cls.archive = _load("bootstrap_archive", ROOT / "scripts" / "build_plugin_archive.py")

    def test_manifest_binds_exact_producer_contracts_sizes_and_hashes(self) -> None:
        self.assertEqual(MANIFEST["producer_source_commit"], "77ded2724ad520ac8e3fcd3f7c1c865ce4a5ce14")
        self.assertEqual(MANIFEST["production_producer_commit"], "bb673a7806850337258b253364b3a88eb92645e7")
        self.assertEqual(MANIFEST["contracts"], {
            "aggregate_schema_version": 2,
            "estimator_method_version": "empirical-v3",
            "receipt_schema_version": 3,
            "result_method_version": "empirical-sim-v2",
            "result_schema_version": 2,
        })
        bootstrap_receipt = json.loads(
            (FIXTURE_ROOT / "bootstrap" / "maintenance-receipt.json").read_text(encoding="utf-8")
        )
        promoted_receipt = json.loads(
            (FIXTURE_ROOT / "promoted" / "maintenance-receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            promoted_receipt["calibration_baseline_receipt_sha256"],
            bootstrap_receipt["receipt_sha256"],
        )
        self.assertEqual(
            promoted_receipt["backtest_outcome"]["baseline_duration_comparison"],
            "performed",
        )
        for kind, fixture in MANIFEST["fixtures"].items():
            receipt = json.loads((FIXTURE_ROOT / kind / "maintenance-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["receipt_sha256"], fixture["receipt_sha256"])
            declared_names = [member["name"] for member in fixture["members"]]
            self.assertEqual(declared_names, sorted(path.name for path in (FIXTURE_ROOT / kind).iterdir()))
            for member in fixture["members"]:
                payload = (FIXTURE_ROOT / kind / member["name"]).read_bytes()
                self.assertEqual(len(payload), member["size"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), member["sha256"])

    def test_exact_bootstrap_and_promoted_producer_bytes_pass_real_verifier_and_archive_readback(self) -> None:
        for kind in ("bootstrap", "promoted"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=ROOT) as temporary:
                root = Path(temporary)
                _stage(root, kind)
                ok, lines = self.verifier.verify_maintenance(root, expected_version="6.2.0", today=date(2026, 8, 21))
                self.assertTrue(ok, lines)
                maintenance = self.archive.admit_maintenance(root, expected_version="6.2.0", today=date(2026, 8, 21))
                frozen_manifest = synthetic_candidate_manifest()
                mode, bundles = self.archive._classify_from_manifest(PLUGIN, frozen_manifest)
                plan = self.archive._member_plan(PLUGIN, mode=mode, bundles=bundles, maintenance=maintenance)
                record_by_name = {
                    (bundle / record["path"]).as_posix(): record
                    for bundle, records in bundles for record in records
                }
                runtime_payloads = {}
                for bundle, records in bundles:
                    runtime_payloads.update(self.archive._read_runtime_payloads(
                        bundle, self.archive._resolve_in_tree_bundle_leaf(PLUGIN, bundle), records,
                        require_install_mode=False,
                    ))
                tar_bytes, _ = self.archive._emit_canonical_tar(
                    plan, plugin_path=PLUGIN, frozen_manifest=frozen_manifest,
                    record_by_name=record_by_name, runtime_payloads=runtime_payloads,
                    runtime_dir_modes=self.archive._runtime_dir_modes(bundles),
                )
                with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
                    for member in MANIFEST["fixtures"][kind]["members"]:
                        stored = archive.extractfile("project-estimation-data/" + member["name"])
                        self.assertIsNotNone(stored)
                        self.assertEqual(stored.read(), (FIXTURE_ROOT / kind / member["name"]).read_bytes())

    def test_any_exact_producer_byte_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            target = _stage(root, "bootstrap")
            aggregate = target / "aggregate-prior.json"
            aggregate.write_bytes(aggregate.read_bytes() + b" ")
            ok, lines = self.verifier.verify_maintenance(root, expected_version="6.2.0", today=date(2026, 8, 21))
            self.assertFalse(ok)
            self.assertTrue(any("canonical" in line or "inventory" in line for line in lines), lines)

    def test_current_maintenance_is_admitted_for_version_7_0_3(self) -> None:
        ok, lines = self.verifier.verify_maintenance(
            ROOT, expected_version="7.0.3"
        )
        self.assertTrue(ok, lines)

    def test_receipt_state_backtest_baseline_and_aggregate_state_are_cross_bound(self) -> None:
        mutations = (
            ("bootstrap", lambda target: self._mutate_backtest(target)),
            ("promoted", lambda target: self._remove_promoted_baseline(target)),
            ("bootstrap", lambda target: self._mismatch_aggregate_state(target)),
            ("bootstrap", lambda target: self._add_bootstrap_duration_comparison(target)),
            ("promoted", lambda target: self._remove_promoted_duration_comparison(target)),
        )
        for kind, mutate in mutations:
            with self.subTest(kind=kind, mutation=mutate.__name__), tempfile.TemporaryDirectory(dir=ROOT) as temporary:
                root = Path(temporary)
                target = _stage(root, kind)
                mutate(target)
                ok, _ = self.verifier.verify_maintenance(root, expected_version="6.2.0", today=date(2026, 8, 21))
                self.assertFalse(ok)

    @staticmethod
    def _mutate_backtest(target: Path) -> None:
        path = target / "maintenance-receipt.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["backtest_outcome"].update({"evaluation_mode": "promotion_gate", "policy_result": "passed"})
        path.write_bytes(CANONICAL(receipt))
        _rebind_receipt(target)

    @staticmethod
    def _remove_promoted_baseline(target: Path) -> None:
        path = target / "maintenance-receipt.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["calibration_baseline_receipt_sha256"] = None
        path.write_bytes(CANONICAL(receipt))
        _rebind_receipt(target)

    @staticmethod
    def _mismatch_aggregate_state(target: Path) -> None:
        path = target / "aggregate-prior.json"
        aggregate = json.loads(path.read_text(encoding="utf-8"))
        aggregate["calibration_state"] = "promoted"
        aggregate["limitations"].remove("bootstrap_descriptive_only")
        path.write_bytes(CANONICAL(aggregate))
        _rebind_receipt(target)

    @staticmethod
    def _add_bootstrap_duration_comparison(target: Path) -> None:
        path = target / "maintenance-receipt.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["backtest_outcome"]["baseline_duration_comparison"] = "performed"
        path.write_bytes(CANONICAL(receipt))
        _rebind_receipt(target)

    @staticmethod
    def _remove_promoted_duration_comparison(target: Path) -> None:
        path = target / "maintenance-receipt.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["backtest_outcome"]["baseline_duration_comparison"] = "not_applicable"
        path.write_bytes(CANONICAL(receipt))
        _rebind_receipt(target)

    def test_enhancement_bootstrap_is_descriptive_and_token_cost_is_typed_unavailable(self) -> None:
        aggregate, pricing, quota = _documents("bootstrap")
        request = json.loads((ROOT / "tests" / "fixtures" / "project_estimation" / "request-enhancement.json").read_text())
        request["as_of_date"] = "2026-08-21"
        result = self.estimator.estimate(request, aggregate, pricing, quota)
        self.assertEqual((result["schema_version"], result["estimator_method_version"]), (2, "empirical-sim-v2"))
        calibration = result["headline"]["calibration"]
        self.assertEqual(calibration["state"], "bootstrap")
        self.assertEqual(calibration["evidence_through_date"], "2026-08-21")
        self.assertEqual(calibration["confidence_basis"], "bootstrap_descriptive")
        self.assertNotEqual(calibration["confidence"], "high")
        self.assertIn("token_prior_unavailable", calibration["limitations"])
        cost = result["headline"]["api_equivalent_cost_current"]
        self.assertEqual(cost, {
            "status": "unavailable_no_token_prior",
            "known_microusd": {"p50": None, "p80": None, "p95": None},
            "known_basis_points": 0,
            "unpriced_basis_points": 0,
        })
        self.assertEqual(result["headline"]["evidence_coverage"]["token_basis_points"], 0)
        self.assertEqual(result["headline"]["evidence_coverage"]["pricing_basis_points"], 0)
        self.assertEqual(result["detail"]["token_class_quantities"], [])
        self.assertEqual(result["detail"]["actual_marginal_cash_status"], "unknown")
        self.assertEqual(calibration["metric_support"]["wait_class"]["status"], "unavailable")
        self.assertEqual(calibration["metric_support"]["rework_review"]["status"], "unavailable")

    def test_unsupported_greenfield_returns_no_compatible_prior(self) -> None:
        aggregate, pricing, quota = _documents("bootstrap")
        request = json.loads((ROOT / "tests" / "fixtures" / "project_estimation" / "request-enhancement.json").read_text())
        request["project_type"] = "greenfield"
        request["as_of_date"] = "2026-08-21"
        result = self.estimator.estimate(request, aggregate, pricing, quota)
        self.assertEqual(result["estimate_unavailable"], "no_compatible_prior")
        self.assertEqual((result["schema_version"], result["estimator_method_version"]), (2, "empirical-sim-v2"))

    def test_result_validation_cross_binds_bootstrap_metadata_and_metric_coverage(self) -> None:
        aggregate, pricing, quota = _documents("bootstrap")
        request = json.loads((ROOT / "tests" / "fixtures" / "project_estimation" / "request-enhancement.json").read_text())
        request["as_of_date"] = "2026-08-21"
        result = self.estimator.estimate(request, aggregate, pricing, quota)
        mutations = (
            lambda forged: forged["headline"]["evidence_coverage"].update({"token_basis_points": 10_000}),
            lambda forged: forged["headline"]["calibration"].update({"evidence_through_date": "2026-08-20"}),
            lambda forged: forged["headline"]["calibration"]["limitations"].remove("bootstrap_descriptive_only"),
            lambda forged: forged["headline"]["calibration"]["metric_support"].update({"actual_marginal_cash": {"status": "published", "eligible_count": 1}}),
            lambda forged: forged["headline"]["calibration"]["metric_support"].update({"quota_delay": {"status": "suppressed_below_k", "eligible_count": None}}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                forged = copy.deepcopy(result)
                mutate(forged)
                with self.assertRaises(self.estimator.EstimationError):
                    self.estimator.validate_result(forged)

    def test_public_production_and_compatibility_json_have_no_private_leakage(self) -> None:
        forbidden_keys = {
            "author", "branch", "commit_sha", "observation_id", "path", "pr_number",
            "pull_request", "raw", "repository", "session_id",
        }
        forbidden_strings = ("/" + "Users/", "/" + "private/", "file" + "://", "@users." + "noreply.github.com")
        files = [*FIXTURE_ROOT.glob("*/*.json"), *DATA.glob("*.json")]
        for path in files:
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                if path.name.endswith(".schema.json"):
                    continue
                stack = [document]
                while stack:
                    value = stack.pop()
                    if isinstance(value, dict):
                        self.assertFalse(forbidden_keys & set(value))
                        stack.extend(value.values())
                    elif isinstance(value, list):
                        stack.extend(value)
                    elif isinstance(value, str):
                        self.assertFalse(any(anchor in value for anchor in forbidden_strings))


class StagedSchemaContractTests(unittest.TestCase):
    def test_closed_schema_versions_and_staged_fields_match_producer(self) -> None:
        aggregate = json.loads((DATA / "aggregate-prior.schema.json").read_text())
        receipt = json.loads((DATA / "maintenance-receipt.schema.json").read_text())
        result = json.loads((DATA / "estimate-result.schema.json").read_text())
        self.assertEqual(aggregate["properties"]["schema_version"], {"const": 2})
        self.assertEqual(aggregate["properties"]["estimator_method_version"], {"const": "empirical-v3"})
        self.assertTrue({"calibration_state", "excluded_observation_count_floor", "exclusion_count_rounding", "limitations"} <= set(aggregate["required"]))
        self.assertIn("metric_support", aggregate["$defs"]["node"]["required"])
        self.assertEqual(receipt["properties"]["schema_version"], {"const": 3})
        self.assertTrue({"calibration_state", "calibration_baseline_receipt_sha256"} <= set(receipt["required"]))
        self.assertEqual(set(receipt["$defs"]["backtest"]["required"]), {"evaluation_mode", "policy_result", "baseline_duration_comparison", "baseline_token_comparison", "warning_codes"})
        self.assertEqual(result["properties"]["schema_version"], {"const": 2})
        self.assertEqual(result["properties"]["estimator_method_version"], {"const": "empirical-sim-v2"})
        self.assertEqual(set(result["$defs"]["headline_cost"]["properties"]["status"]["enum"]), {"available", "partial_unpriced", "unavailable_no_token_prior"})
        self.assertTrue({"state", "evidence_through_date", "limitations", "confidence_basis", "metric_support", "excluded_observation_count_floor", "exclusion_count_rounding"} <= set(result["$defs"]["calibration"]["required"]))


if __name__ == "__main__":
    unittest.main()
