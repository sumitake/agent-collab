"""Direct runtime release-gate contract."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from tests.test_direct_runtime_public_contract import _wire_descriptor


ROOT = Path(__file__).resolve().parents[1]


class ReleaseRuntimeGateTests(unittest.TestCase):
    @staticmethod
    def _load_gate(name: str):
        path = ROOT / "scripts" / "verify_runtime_release.py"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_release_gate_uses_shared_schema4_validator_and_notarization_gate(self) -> None:
        path = ROOT / "scripts" / "verify_runtime_release.py"
        spec = importlib.util.spec_from_file_location("direct_release_gate", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.runtime_client.validate_manifest_document))
        self.assertFalse(hasattr(module, "REQUIRED_CONTRACTS"))
        self.assertIn("--check-notarization", path.read_text(encoding="utf-8"))

    def test_release_manifest_loader_rejects_duplicate_keys(self) -> None:
        import tempfile

        path = ROOT / "scripts" / "verify_runtime_release.py"
        spec = importlib.util.spec_from_file_location("strict_release_gate", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        descriptor, digest = _wire_descriptor()
        manifest = {
            "schema_version": 4,
            "protocol_version": 4,
            "contract_version": 4,
            "wire_contract": descriptor,
            "wire_contract_sha256": digest,
            "channel": "production",
            "artifacts": [],
        }
        encoded = json.dumps(manifest, separators=(",", ":"))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / module.MANIFEST_REL
            target.parent.mkdir(parents=True)
            target.write_text('{"schema_version":4,' + encoded[1:], encoding="utf-8")
            data, _path, errors = module._manifest(root)
        self.assertIsNone(data)
        self.assertEqual(errors, ["runtime manifest is unreadable"])

    def test_codesign_tool_failure_has_stable_unavailable_reason(self) -> None:
        module = self._load_gate("codesign_unavailable_release_gate")
        signing = {
            "team_id": "ABCDEFGHIJ",
            "identity": "Developer ID Application: Test Runtime (ABCDEFGHIJ)",
        }
        with mock.patch.object(module.subprocess, "run", side_effect=OSError("denied")):
            _evidence, errors = module._verify_member_signature(
                Path("runtime"), signing=signing, assess_notarization=True
            )
        self.assertEqual(
            errors,
            [
                "codesign_check_unavailable: "
                "macOS code-signing verification tool failed"
            ],
        )

    def test_nonzero_notarization_check_is_neutral_not_rejection(self) -> None:
        module = self._load_gate("notarization_neutral_release_gate")
        signing = {
            "team_id": "ABCDEFGHIJ",
            "identity": "Developer ID Application: Test Runtime (ABCDEFGHIJ)",
        }
        detail = "\n".join(
            (
                "Authority=Developer ID Application: Test Runtime (ABCDEFGHIJ)",
                "TeamIdentifier=ABCDEFGHIJ",
                "flags=0x10000(runtime)",
                "Timestamp=Aug 24, 2026 at 00:00:00",
            )
        )
        successful = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        detailed = subprocess.CompletedProcess([], 0, stdout="", stderr=detail)
        not_confirmed = subprocess.CompletedProcess([], 3, stdout="", stderr="")
        with mock.patch.object(
            module.subprocess,
            "run",
            side_effect=(successful, detailed, not_confirmed),
        ):
            _evidence, errors = module._verify_member_signature(
                Path("runtime"), signing=signing, assess_notarization=True
            )
        self.assertEqual(
            errors,
            [
                "notarization_not_confirmed: codesign '=notarized' "
                "requirement did not confirm notarization"
            ],
        )


if __name__ == "__main__":
    unittest.main()
