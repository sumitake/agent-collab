"""Activation release must consume macOS signing/notarization evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_runtime_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_runtime_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseRuntimeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = _load()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugins" / "agent-collab"
        self.plugin.mkdir(parents=True)
        (self.plugin / "signing_policy.py").write_text(
            'EXPECTED_DEVELOPER_ID_TEAM = "TESTTEAM01"\n', encoding="utf-8"
        )
        self.team_patch = mock.patch.object(
            self.gate, "EXPECTED_DEVELOPER_ID_TEAM", "TESTTEAM01"
        )
        self.team_patch.start()

    def tearDown(self) -> None:
        self.team_patch.stop()
        self.temp.cleanup()

    def test_unconfigured_operator_team_blocks_activation(self) -> None:
        self._manifest(set(self.gate.REQUIRED_CONTRACTS))
        with mock.patch.object(self.gate, "EXPECTED_DEVELOPER_ID_TEAM", ""):
            ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertFalse(ok)
        self.assertTrue(any("Team ID is not configured" in error for error in errors))

    def test_manifest_team_must_equal_pinned_operator_team(self) -> None:
        path = self._manifest(set(self.gate.REQUIRED_CONTRACTS))
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["artifacts"][0]["signing"]["team_id"] = "OTHERTEAM1"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertFalse(ok)
        self.assertTrue(any("platform/signing" in error for error in errors))

    def _manifest(self, contracts: set[tuple[str, str]]) -> Path:
        bundle = (
            self.plugin
            / "runtime"
            / "darwin-arm64"
            / "agent-collab-runtime.bundle"
        )
        bundle.mkdir(parents=True, exist_ok=True)
        binary = bundle / "agent-collab-runtime"
        bundle.chmod(0o700)
        if binary.exists():
            binary.chmod(0o700)
        binary.write_bytes(b"signed-runtime-fixture")
        binary.chmod(0o500)
        bundle.chmod(0o500)
        records = [
            {
                "path": "agent-collab-runtime",
                "role": "entrypoint",
                "install_mode": 0o500,
                "size": binary.stat().st_size,
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "macho_type": "executable",
                "architecture": "arm64",
                "minimum_macos": "14.0",
                "signing_profile": "production_developer_id",
            }
        ]
        manifest = {
            "schema_version": 3,
            "protocol_version": 2,
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
                    "size": binary.stat().st_size,
                    "sha256": self.gate.runtime_bundle.compute_bundle_identity(records),
                    "provider_runtime_version": "2.0.0",
                    "route_contract_version": 2,
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
                        for route, action in sorted(contracts)
                    ],
                }
            ],
        }
        path = self.plugin / "runtime-manifest.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_empty_manifest_blocks_activation(self) -> None:
        (self.plugin / "runtime-manifest.json").write_text(
            '{"schema_version":3,"protocol_version":2,"contract_version":3,"broker_protocol_version":2,"channel":"production","artifacts":[]}'
        )
        ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertFalse(ok)
        self.assertTrue(any("artifact" in error for error in errors))

    def test_missing_signing_policy_blocks_activation(self) -> None:
        self._manifest(set(self.gate.REQUIRED_CONTRACTS))
        (self.plugin / "signing_policy.py").unlink()
        ok, evidence, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertFalse(ok)
        self.assertEqual(evidence, {})
        self.assertTrue(any("signing policy" in error for error in errors))

    def test_missing_matrix_row_blocks_activation(self) -> None:
        self._manifest({("codex", "advisory")})
        ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertFalse(ok)
        self.assertTrue(any("contract" in error for error in errors))

    def test_release_size_limit_matches_published_manifest_schema(self) -> None:
        schema = json.loads(
            (ROOT / "plugins" / "agent-collab" / "runtime-manifest.schema.json").read_text()
        )
        maximum = schema["properties"]["artifacts"]["items"]["properties"][
            "size"
        ]["maximum"]
        self.assertEqual(self.gate.MAX_ARTIFACT_BYTES, 64 * 1024 * 1024)
        self.assertGreaterEqual(maximum, self.gate.MAX_ARTIFACT_BYTES)

    def test_evidence_is_bound_to_git_manifest_and_artifact_digests(self) -> None:
        self._manifest(set(self.gate.REQUIRED_CONTRACTS))
        def run(command, **_kwargs):
            if command[0] == "/usr/bin/lipo":
                return mock.Mock(returncode=0, stdout="arm64\n", stderr="")
            if command[0] == "/usr/bin/otool":
                if "-hv" in command:
                    return mock.Mock(
                        returncode=0,
                        stdout="MH_MAGIC_64 ARM64 ALL 0x00 EXECUTE 21 1688\n",
                        stderr="",
                    )
                return mock.Mock(
                    returncode=0,
                    stdout=(
                        "Load command 9\n"
                        "      cmd LC_BUILD_VERSION\n"
                        " platform 1\n"
                        "    minos 14.0\n"
                    ),
                    stderr="",
                )
            if command[0] == "/usr/bin/codesign" and "-dv" in command:
                return mock.Mock(
                    returncode=0,
                    stdout="",
                    stderr=(
                        "Authority=Developer ID Application: Test Operator (TESTTEAM01)\n"
                        "TeamIdentifier=TESTTEAM01 flags=0x10000(runtime)\n"
                        "Timestamp=Jul 12, 2026 at 12:00:00\n"
                    ),
                )
            return mock.Mock(
                returncode=0,
                stdout="",
                stderr="accepted\nsource=Notarized Developer ID\n",
            )

        with (
            mock.patch.object(self.gate.subprocess, "run", side_effect=run),
            mock.patch.object(self.gate.platform, "system", return_value="Darwin"),
            mock.patch.object(self.gate.platform, "machine", return_value="arm64"),
        ):
            ok, evidence, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertTrue(ok, errors)
        evidence_path = self.root / "evidence.json"
        evidence_path.write_text(json.dumps(evidence))
        self.assertEqual(
            self.gate.verify_evidence(self.root, evidence_path, git_sha="abc"), []
        )
        policy_digest = hashlib.sha256(
            (self.plugin / "signing_policy.py").read_bytes()
        ).hexdigest()
        self.assertEqual(evidence["signing_policy_sha256"], policy_digest)
        tampered = dict(evidence)
        tampered["git_sha"] = "different"
        evidence_path.write_text(json.dumps(tampered))
        self.assertTrue(
            self.gate.verify_evidence(self.root, evidence_path, git_sha="abc")
        )

        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        (self.plugin / "signing_policy.py").write_text(
            'EXPECTED_DEVELOPER_ID_TEAM = "OTHERTEAM1"\n', encoding="utf-8"
        )
        self.assertTrue(
            any(
                "signing policy" in error
                for error in self.gate.verify_evidence(
                    self.root, evidence_path, git_sha="abc"
                )
            )
        )

    def test_release_rejects_runtime_filename_without_hardened_flag(self) -> None:
        self._manifest(set(self.gate.REQUIRED_CONTRACTS))
        def run(command, **_kwargs):
            if command[0] == "/usr/bin/lipo":
                return mock.Mock(returncode=0, stdout="arm64\n", stderr="")
            if command[0] == "/usr/bin/otool":
                if "-hv" in command:
                    return mock.Mock(
                        returncode=0,
                        stdout="MH_MAGIC_64 ARM64 ALL 0x00 EXECUTE 21 1688\n",
                        stderr="",
                    )
                return mock.Mock(
                    returncode=0,
                    stdout=(
                        "Load command 9\n"
                        "      cmd LC_BUILD_VERSION\n"
                        " platform 1\n"
                        "    minos 14.0\n"
                    ),
                    stderr="",
                )
            if command[0] == "/usr/bin/codesign" and "-dv" in command:
                return mock.Mock(
                    returncode=0,
                    stdout="",
                    stderr=(
                        "Executable=/tmp/agent-collab-runtime\n"
                        "Authority=Developer ID Application: Test Operator (TESTTEAM01)\n"
                        "TeamIdentifier=TESTTEAM01\n"
                        "Timestamp=Jul 12, 2026 at 12:00:00\n"
                        "CodeDirectory v=20500 flags=0x0(none)\n"
                    ),
                )
            return mock.Mock(
                returncode=0,
                stdout="",
                stderr="accepted\nsource=Notarized Developer ID\n",
            )

        with (
            mock.patch.object(self.gate.subprocess, "run", side_effect=run),
            mock.patch.object(self.gate.platform, "system", return_value="Darwin"),
            mock.patch.object(self.gate.platform, "machine", return_value="arm64"),
        ):
            ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
        self.assertFalse(ok)
        self.assertTrue(any("hardened" in error for error in errors))

    def test_release_inspects_macho_architecture_and_build_minimum(self) -> None:
        valid_build = """Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 14.0
      sdk 15.0
   ntools 1
"""
        cases = (
            ("x86_64", valid_build, False),
            ("arm64 x86_64", valid_build, False),
            (
                "arm64",
                "Load command 9\n      cmd LC_VERSION_MIN_MACOSX\n  version 14.0\n",
                False,
            ),
            ("arm64", valid_build.replace("minos 14.0", "minos 13.0"), False),
            ("arm64", valid_build, True),
        )
        for architectures, load_commands, expected in cases:
            with self.subTest(architectures=architectures, expected=expected):
                self._manifest(set(self.gate.REQUIRED_CONTRACTS))

                def run(command, **_kwargs):
                    if command[0] == "/usr/bin/lipo":
                        return mock.Mock(returncode=0, stdout=architectures + "\n", stderr="")
                    if command[0] == "/usr/bin/otool":
                        if "-hv" in command:
                            return mock.Mock(
                                returncode=0,
                                stdout="MH_MAGIC_64 ARM64 ALL 0x00 EXECUTE 21 1688\n",
                                stderr="",
                            )
                        return mock.Mock(returncode=0, stdout=load_commands, stderr="")
                    if command[0] == "/usr/bin/codesign" and "-dv" in command:
                        return mock.Mock(
                            returncode=0,
                            stdout="",
                            stderr=(
                                "Authority=Developer ID Application: Test Operator (TESTTEAM01)\n"
                                "TeamIdentifier=TESTTEAM01 flags=0x10000(runtime)\n"
                                "Timestamp=Jul 12, 2026 at 12:00:00\n"
                            ),
                        )
                    return mock.Mock(
                        returncode=0,
                        stdout="",
                        stderr="accepted\nsource=Notarized Developer ID\n",
                    )

                with (
                    mock.patch.object(self.gate.subprocess, "run", side_effect=run),
                    mock.patch.object(self.gate.platform, "system", return_value="Darwin"),
                    mock.patch.object(self.gate.platform, "machine", return_value="arm64"),
                ):
                    ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
                self.assertEqual(ok, expected, errors)
                if not expected:
                    self.assertTrue(any("Mach-O" in error for error in errors), errors)

    def test_release_requires_secure_timestamp_and_notarization(self) -> None:
        valid_build = (
            "Load command 9\n"
            "      cmd LC_BUILD_VERSION\n"
            " platform 1\n"
            "    minos 14.0\n"
        )
        # (timestamp, notarized, expected). Notarization is now verified with
        # `codesign --verify --strict --test-requirement '=notarized'` (exit 0 =
        # notarized), not `spctl --assess` — the runtime is a bare CLI Mach-O,
        # which spctl cannot assess.
        cases = (
            ("", True, False),
            ("Timestamp=none", True, False),
            ("Timestamp=Jul 12, 2026 at 12:00:00", False, False),
            ("Timestamp=Jul 12, 2026 at 12:00:00", True, True),
        )
        for timestamp, notarized, expected in cases:
            with self.subTest(timestamp=timestamp, notarized=notarized):
                self._manifest(set(self.gate.REQUIRED_CONTRACTS))

                codesign_calls = []

                def run(command, **_kwargs):
                    codesign_calls.append(list(command))
                    if command[0] == "/usr/bin/lipo":
                        return mock.Mock(returncode=0, stdout="arm64\n", stderr="")
                    if command[0] == "/usr/bin/otool":
                        if "-hv" in command:
                            return mock.Mock(
                                returncode=0,
                                stdout="MH_MAGIC_64 ARM64 ALL 0x00 EXECUTE 21 1688\n",
                                stderr="",
                            )
                        return mock.Mock(returncode=0, stdout=valid_build, stderr="")
                    if command[0] == "/usr/bin/codesign" and "-dv" in command:
                        return mock.Mock(
                            returncode=0,
                            stdout="",
                            stderr=(
                                "Authority=Developer ID Application: Test Operator (TESTTEAM01)\n"
                                "TeamIdentifier=TESTTEAM01\n"
                                "CodeDirectory v=20500 flags=0x10000(runtime)\n"
                                f"{timestamp}\n"
                            ),
                        )
                    if (
                        command[0] == "/usr/bin/codesign"
                        and "--test-requirement" in command
                    ):
                        # The notarization gate: exit 0 iff the =notarized
                        # requirement is satisfied.
                        return mock.Mock(
                            returncode=0 if notarized else 3, stdout="", stderr=""
                        )
                    return mock.Mock(returncode=0, stdout="", stderr="valid")

                with (
                    mock.patch.object(self.gate.subprocess, "run", side_effect=run),
                    mock.patch.object(self.gate.platform, "system", return_value="Darwin"),
                    mock.patch.object(self.gate.platform, "machine", return_value="arm64"),
                ):
                    ok, evidence, errors = self.gate.verify_release(
                        self.root, git_sha="abc"
                    )
                self.assertEqual(ok, expected, errors)
                # Notarization is asserted via the codesign requirement command
                # shape (never spctl), and the exact `=notarized` predicate with
                # --strict and WITHOUT --check-notarization (which would fail open).
                notar = [
                    c
                    for c in codesign_calls
                    if c[0] == "/usr/bin/codesign" and "--test-requirement" in c
                ]
                self.assertEqual(len(notar), 1)
                self.assertIn("--strict", notar[0])
                self.assertEqual(notar[0][notar[0].index("--test-requirement") + 1], "=notarized")
                self.assertNotIn("--check-notarization", notar[0])
                self.assertFalse(any(c and c[0] == "/usr/sbin/spctl" for c in codesign_calls))
                if expected:
                    self.assertEqual(
                        evidence["spctl_source"], "Notarized Developer ID"
                    )
                    self.assertEqual(evidence["codesign_timestamp"], timestamp[10:])
                else:
                    self.assertTrue(
                        any(
                            "Timestamp" in error or "notarized" in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_release_notarization_tool_failure_is_fail_closed(self) -> None:
        valid_build = (
            "Load command 9\n"
            "      cmd LC_BUILD_VERSION\n"
            " platform 1\n"
            "    minos 14.0\n"
        )
        # If the notarization codesign call raises (missing tool / timeout), the
        # gate must fail closed — an un-run check is never treated as notarized.
        for exc in (
            OSError("codesign missing"),
            self.gate.subprocess.TimeoutExpired(cmd="codesign", timeout=30),
        ):
            with self.subTest(exc=type(exc).__name__):
                self._manifest(set(self.gate.REQUIRED_CONTRACTS))

                def run(command, **_kwargs):
                    if command[0] == "/usr/bin/lipo":
                        return mock.Mock(returncode=0, stdout="arm64\n", stderr="")
                    if command[0] == "/usr/bin/otool":
                        if "-hv" in command:
                            return mock.Mock(
                                returncode=0,
                                stdout="MH_MAGIC_64 ARM64 ALL 0x00 EXECUTE 21 1688\n",
                                stderr="",
                            )
                        return mock.Mock(returncode=0, stdout=valid_build, stderr="")
                    if command[0] == "/usr/bin/codesign" and "-dv" in command:
                        return mock.Mock(
                            returncode=0,
                            stdout="",
                            stderr=(
                                "Authority=Developer ID Application: Test Operator (TESTTEAM01)\n"
                                "TeamIdentifier=TESTTEAM01\n"
                                "CodeDirectory v=20500 flags=0x10000(runtime)\n"
                                "Timestamp=Jul 12, 2026 at 12:00:00\n"
                            ),
                        )
                    if (
                        command[0] == "/usr/bin/codesign"
                        and "--test-requirement" in command
                    ):
                        raise exc
                    return mock.Mock(returncode=0, stdout="", stderr="valid")

                with (
                    mock.patch.object(self.gate.subprocess, "run", side_effect=run),
                    mock.patch.object(self.gate.platform, "system", return_value="Darwin"),
                    mock.patch.object(self.gate.platform, "machine", return_value="arm64"),
                ):
                    ok, _, errors = self.gate.verify_release(self.root, git_sha="abc")
                self.assertFalse(ok)
                self.assertTrue(
                    any("verification tool failed" in error for error in errors),
                    errors,
                )

    def test_workflow_and_tools_have_no_unsigned_or_ignored_tag_path(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        merge_tool = (ROOT / "scripts" / "merge-and-tag.py").read_text()
        cut_tool = (ROOT / "scripts" / "cut_release.py").read_text()
        self.assertIn("verify-runtime-macos", workflow)
        self.assertIn("verify-release-ref", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("runtime-verification", workflow)
        self.assertIn("runs-on: macos-15", workflow)
        self.assertNotIn("runs-on: macos-14", workflow)
        self.assertIn("build_plugin_archive.py", workflow)
        self.assertIn("build_release_evidence.py", workflow)
        self.assertIn(".sha256", workflow)
        self.assertIn(".spdx.json", workflow)
        self.assertIn("policy-only", workflow)
        self.assertIn(".verification.verified", workflow)
        self.assertIn("merge-base --is-ancestor", workflow)
        self.assertIn("origin/main", workflow)
        self.assertIn("Materialize signed annotated release tag object", workflow)
        self.assertIn(
            "Verify active tree and reachable history are safe for public packaging",
            workflow,
        )
        materialize = workflow.index(
            "Materialize signed annotated release tag object"
        )
        history_gate = workflow.index(
            "Verify active tree and reachable history are safe for public packaging"
        )
        self.assertLess(materialize, history_gate)
        self.assertIn(
            'git fetch --force origin "${TAG_REF}:${TAG_REF}"', workflow
        )
        self.assertIn('test "$(git cat-file -t "$TAG_REF")" = tag', workflow)
        self.assertNotIn('run_cmd(["git", "tag", tag_name', merge_tool)
        self.assertNotIn('run_cmd(["git", "push", "origin", tag_name', merge_tool)
        self.assertIn("verify_runtime_release.py", cut_tool)
        self.assertIn('"tag", "-s"', cut_tool)
        self.assertIn('"verify-tag", tag', cut_tool)
        self.assertIn('"merge-base"', cut_tool)
        self.assertIn('"--is-ancestor"', cut_tool)


if __name__ == "__main__":
    unittest.main()
