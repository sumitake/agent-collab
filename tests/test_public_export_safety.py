"""Direct-runtime public export contract."""

import importlib.util
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class PublicExportSafetyTests(unittest.TestCase):
    def test_development_only_paths_are_rejected_from_tree_and_archives(self) -> None:
        module = self._module()
        prohibited = {
            "_dev_route_evidence.py",
            "development-provenance.json",
            "development-route-evidence",
            "development-route-evidence.key",
            "manage_route_promotions.py",
        }
        for name in prohibited:
            relative = Path("nested") / name
            issue = module._path_violation(Path("/tmp") / relative, relative)
            self.assertIsNotNone(issue, name)
            self.assertEqual(issue.kind, "development_only_path")

            payload = io.BytesIO()
            with zipfile.ZipFile(payload, mode="w") as archive:
                archive.writestr(f"nested/{name}", b"bounded")
            violations = module._archive_violations(payload.getvalue(), "fixture.zip")
            self.assertTrue(
                any(
                    item.kind == "development_only_path"
                    and item.evidence.endswith(f"nested/{name}")
                    for item in violations
                ),
                (name, violations),
            )

    def test_export_gate_uses_the_shared_manifest_validator(self) -> None:
        path = ROOT / "scripts" / "check-public-export-safety.py"
        spec = importlib.util.spec_from_file_location("direct_export", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.runtime_client.validate_manifest_document))
        self.assertFalse(hasattr(module, "REQUIRED_RUNTIME_CONTRACTS"))

    def test_runtime_contract_scan_rejects_duplicate_key_manifest(self) -> None:
        module = self._module()
        with tempfile.TemporaryDirectory() as raw:
            root = self._root_with_duplicate_manifest(Path(raw), module)
            relative = next(
                path
                for path in module.RUNTIME_BUNDLE_RELS
                if "darwin-arm64" in path.as_posix()
            ) / "agent-collab-runtime"
            violation = module._runtime_contract_violation(root, relative, b"bytes")
            self.assertIsNotNone(violation)
            self.assertEqual(violation.kind, "unmanifested_runtime")

    def _module(self):
        path = ROOT / "scripts" / "check-public-export-safety.py"
        spec = importlib.util.spec_from_file_location("strict_direct_export", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _root_with_duplicate_manifest(self, root: Path, module) -> Path:
        from tests.test_direct_runtime_public_contract import _wire_descriptor

        plugin = root / "plugins" / "agent-collab"
        plugin.mkdir(parents=True)
        bundle = root / next(
            path
            for path in module.RUNTIME_BUNDLE_RELS
            if "darwin-arm64" in path.as_posix()
        )
        bundle.mkdir(parents=True)
        member = bundle / "agent-collab-runtime"
        member.write_bytes(b"bytes")
        member.chmod(0o755)

        descriptor, digest = _wire_descriptor()
        member_digest = hashlib.sha256(b"bytes").hexdigest()
        records = [
            {
                "architecture": "arm64",
                "install_mode": 0o500,
                "macho_type": "executable",
                "minimum_macos": "14.0",
                "path": "agent-collab-runtime",
                "role": "entrypoint",
                "sha256": member_digest,
                "signing_profile": "production_developer_id",
                "size": len(b"bytes"),
            }
        ]
        manifest = {
            "schema_version": 4,
            "protocol_version": 4,
            "contract_version": 4,
            "wire_contract": descriptor,
            "wire_contract_sha256": digest,
            "channel": "production",
            "artifacts": [
                {
                    "platform": "darwin",
                    "arch": "arm64",
                    "kind": "standalone_bundle",
                    "minimum_macos": "14.0",
                    "path": "runtime/darwin-arm64/agent-collab-runtime.bundle",
                    "entrypoint": "agent-collab-runtime",
                    "size": len(b"bytes"),
                    "sha256": module.runtime_bundle.compute_bundle_identity(records),
                    "provider_runtime_version": "4.0.0",
                    "signing": {
                        "mode": "developer_id",
                        "identity": "Developer ID Application: Test (ABCDEFGHIJ)",
                        "team_id": "ABCDEFGHIJ",
                        "require_notarization": True,
                        "hardened_runtime": True,
                        "secure_timestamp": True,
                    },
                    "files": records,
                }
            ],
        }
        encoded = json.dumps(manifest, separators=(",", ":"))
        (plugin / "runtime-manifest.json").write_text(
            '{"schema_version":4,' + encoded[1:], encoding="utf-8"
        )
        (plugin / "signing_policy.py").write_text(
            'EXPECTED_DEVELOPER_ID_TEAM = "ABCDEFGHIJ"\n', encoding="utf-8"
        )
        return root


if __name__ == "__main__":
    unittest.main()
