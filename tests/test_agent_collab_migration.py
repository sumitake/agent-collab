"""Deterministic migration-doctor and startup-preflight policy tests."""

from __future__ import annotations

import importlib.util
import dataclasses
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
NATIVE_CAPABILITIES = (
    "gemini_advisory",
    "gemini_governance",
    "gemini_long_context",
    "codex_advisory",
    "opencode_plan",
    "opencode_build",
    "grok_architecture",
    "grok_governance",
    "grok_huge_context",
    "composer_codegen",
)


def _load(name: str):
    path = PLUGIN / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"agent_collab_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MigrationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = _load("host_policy")
        cls.doctor = _load("migration_doctor")

    def setUp(self) -> None:
        self.identity_env = mock.patch.dict(os.environ, {}, clear=True)
        self.identity_env.start()
        self.addCleanup(self.identity_env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _preflight(self, **kwargs):
        contracts = frozenset(
            {
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
            }
        )
        with mock.patch.object(
            self.policy, "_runtime_contracts", return_value=(contracts, "digest-1")
        ):
            return self.policy.startup_preflight(**kwargs)

    def _write_codex_rollout(
        self,
        *,
        thread_id: str,
        model: str = "gpt-5.6-sol",
        day: str = "19",
    ) -> Path:
        sessions = self.home / "codex-sessions"
        directory = sessions / "2026" / "07" / day
        directory.mkdir(parents=True, mode=0o755, exist_ok=True)
        path = directory / f"rollout-2026-07-{day}T00-00-00-{thread_id}.jsonl"
        records = (
            {
                "type": "session_meta",
                "payload": {"id": thread_id, "model_provider": "openai"},
            },
            {
                "type": "turn_context",
                "payload": {
                    "model": model,
                    "collaboration_mode": {"settings": {"model": model}},
                },
            },
        )
        path.write_text(
            "\n".join(
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in records
            )
            + "\n",
            encoding="utf-8",
        )
        path.chmod(0o644)
        return sessions

    def test_inventory_and_duplicate_state_block_provider_routing(self) -> None:
        legacy = self.home / ".codex" / "plugins" / "codex-collab"
        legacy.mkdir(parents=True)
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertIn("codex-collab", inventory.active_packages)

        outcome = self._preflight(
            governance=False,
            explicit_config={
                "primary_id": "zcode",
                "primary_family": "zhipu",
                "active_model": "opencode/glm-5.2",
                "host_runtime": "opencode",
                "session_identifier": "s-1",
            },
            active_legacy_packages=inventory.active_packages,
            native_capabilities=NATIVE_CAPABILITIES,
            safe_mode=False,
        )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.DUPLICATE_BLOCKED)
        self.assertEqual(outcome.eligible_routes, ())

    def test_inventory_covers_every_historically_public_package_identity(self) -> None:
        self.assertEqual(
            set(self.doctor.LEGACY_PACKAGES),
            {
                "agent-collab-plugin",
                "gemini-collab",
                "grok-collab",
                "claude-collab",
                "codex-collab",
                "antigravity-collab",
                "codex-tools",
                "glm-worker",
                "grok-worker",
            },
        )

    def test_current_marketplace_repo_name_is_not_a_legacy_plugin_selection(self) -> None:
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {
                    "enabledPlugins": {"agent-collab@agent-collab": True},
                    "extraKnownMarketplaces": {
                        "agent-collab": {
                            "source": {
                                "source": "github",
                                "repo": "sumitake/agent-collab",
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertNotIn("agent-collab-plugin", inventory.active_packages)
        self.assertNotIn("agent-collab-plugin", inventory.installed_packages)

    def test_claude_registry_matches_legacy_plugin_identities_exactly(self) -> None:
        settings = self.home / ".claude" / "settings.json"
        installed = self.home / ".claude" / "plugins" / "installed_plugins.json"
        installed.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {
                    "enabledPlugins": {
                        "gemini-collab@agent-collab": True,
                        "agent-collab@agent-collab": True,
                    },
                    "extraKnownMarketplaces": {
                        "agent-collab": {
                            "source": {
                                "source": "github",
                                "repo": "sumitake/agent-collab",
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        installed.write_text(
            json.dumps(
                {
                    "version": 2,
                    "plugins": {
                        "grok-collab@agent-collab": [{"version": "1.0.0"}],
                        "agent-collab@agent-collab": [{"version": "3.0.0"}],
                    },
                }
            ),
            encoding="utf-8",
        )
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertIn("gemini-collab", inventory.active_packages)
        self.assertIn("gemini-collab", inventory.installed_packages)
        self.assertIn("grok-collab", inventory.installed_packages)
        self.assertNotIn("grok-collab", inventory.active_packages)
        self.assertNotIn("agent-collab-plugin", inventory.installed_packages)

    def test_malformed_or_unsafe_existing_registries_fail_inventory_closed(self) -> None:
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{not-json", encoding="utf-8")
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertTrue(inventory.errors)
        self.assertTrue(any("settings.json" in error for error in inventory.errors))

        settings.unlink()
        target = self.home / "external-settings.json"
        target.write_text("{}", encoding="utf-8")
        settings.symlink_to(target)
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertTrue(any("unsafe" in error for error in inventory.errors))

        settings.unlink()
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[plugins."codex-collab"\nenabled = true\n', encoding="utf-8")
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertTrue(any("config.toml" in error for error in inventory.errors))

    def test_home_resolution_failures_are_inventory_errors(self) -> None:
        for failure in (
            KeyError("missing passwd entry"),
            RuntimeError("no home"),
            OSError("unreadable home"),
        ):
            with self.subTest(failure=type(failure).__name__), mock.patch.object(
                self.doctor.Path, "expanduser", side_effect=failure
            ):
                inventory = self.doctor.inventory_legacy_packages(Path("~"))
            self.assertEqual(inventory.active_packages, ())
            self.assertEqual(inventory.installed_packages, ())
            self.assertEqual(
                inventory.errors,
                (f"cannot resolve home directory: {type(failure).__name__}",),
            )

    def test_cli_default_home_resolution_failure_reports_blocked(self) -> None:
        with mock.patch.object(
            self.doctor.Path, "home", side_effect=AssertionError("eager Path.home")
        ), mock.patch.object(
            self.doctor.Path,
            "expanduser",
            side_effect=KeyError("missing passwd entry"),
        ), mock.patch.object(
            self.doctor, "_runtime_state", return_value="available"
        ), mock.patch("builtins.print") as printer:
            code = self.doctor.main(["--json"])
        self.assertEqual(code, 1)
        report = json.loads(printer.call_args.args[0])
        self.assertEqual(report["provider_routing"], "BLOCKED")
        self.assertEqual(
            report["inventory_errors"],
            ["cannot resolve home directory: KeyError"],
        )

    def test_python310_fallback_parses_exact_codex_plugin_subset(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
model = "openai/codex"

[plugins."codex-collab@agent-collab"] # current legacy selection
enabled = true

[plugins."glm-worker@agent-collab"]
enabled = false # installed but disabled

[plugins."agent-collab@agent-collab"]
enabled = true
""".strip()
            + "\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.doctor, "tomllib", None):
            inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertEqual(inventory.errors, ())
        self.assertEqual(inventory.active_packages, ("codex-collab",))
        self.assertEqual(
            inventory.installed_packages, ("codex-collab", "glm-worker")
        )

    def test_python310_fallback_never_substring_matches_legacy_names(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
model_reasoning_summary = "codex-collab and glm-worker are prose only"

[projects."/tmp/codex-collab"]
trust_level = "trusted"

[plugins."codex-collab-extra@agent-collab"]
enabled = true
""".strip()
            + "\n",
            encoding="utf-8",
        )
        with mock.patch.object(self.doctor, "tomllib", None):
            inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertEqual(inventory.errors, ())
        self.assertEqual(inventory.active_packages, ())
        self.assertEqual(inventory.installed_packages, ())

    def test_sanctioned_two_selector_agent_collab_overlap_does_not_trip_legacy_duplicate_block(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
[plugins."agent-collab@agent-collab-dev"]
enabled = true

[plugins."agent-collab@agent-collab-dev-candidate"]
enabled = true
""".strip()
            + "\n",
            encoding="utf-8",
        )
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertEqual(inventory.active_packages, ())
        self.assertEqual(inventory.installed_packages, ())
        self.assertEqual(inventory.errors, ())

        outcome = self._preflight(
            governance=False,
            explicit_config={
                "primary_id": "codex",
                "primary_family": "openai",
                "active_model": "gpt-5",
                "host_runtime": "codex",
                "session_identifier": "candidate-overlap",
            },
            active_legacy_packages=inventory.active_packages,
            safe_mode=False,
        )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        self.assertNotEqual(outcome.status, self.policy.PreflightStatus.DUPLICATE_BLOCKED)

    def test_python310_fallback_rejects_unsupported_plugin_toml(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            'plugins."codex-collab@agent-collab".enabled = true\n',
            encoding="utf-8",
        )
        with mock.patch.object(self.doctor, "tomllib", None):
            inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertEqual(inventory.active_packages, ())
        self.assertEqual(inventory.installed_packages, ())
        self.assertTrue(any("config.toml" in error for error in inventory.errors))

    def test_python310_fallback_blocks_escaped_plugins_root_assignments(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        cases = (
            r'"\U00000070lugins"."codex-collab@agent-collab".enabled = true',
            r'"\U00000070lugins" = {"codex-collab@agent-collab" = {enabled = true}}',
        )
        for statement in cases:
            with self.subTest(statement=statement):
                config.write_text(statement + "\n", encoding="utf-8")
                with mock.patch.object(self.doctor, "tomllib", None):
                    inventory = self.doctor.inventory_legacy_packages(self.home)
                self.assertEqual(inventory.active_packages, ())
                self.assertEqual(inventory.installed_packages, ())
                self.assertTrue(
                    any("config.toml" in error for error in inventory.errors)
                )

    def test_python310_fallback_ignores_plugin_examples_in_multiline_strings(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        for delimiter in ('"""', "'''"):
            with self.subTest(delimiter=delimiter):
                config.write_text(
                    "instructions = "
                    + delimiter
                    + "\n[plugins.\"codex-collab@agent-collab\"]\n"
                    + "enabled = true\n"
                    + delimiter
                    + "\n\n[plugins.\"agent-collab@agent-collab\"]\n"
                    + "enabled = true\n",
                    encoding="utf-8",
                )
                with mock.patch.object(self.doctor, "tomllib", None):
                    inventory = self.doctor.inventory_legacy_packages(self.home)
                self.assertEqual(inventory.errors, ())
                self.assertEqual(inventory.active_packages, ())
                self.assertEqual(inventory.installed_packages, ())

    def test_known_profile_and_safe_mode_exclude_native_routes(self) -> None:
        outcome = self._preflight(
            governance=False,
            explicit_config={
                "primary_id": "zcode",
                "active_model": "opencode/glm-5.2",
                "host_runtime": "opencode",
                "session_identifier": "s-2",
            },
            active_legacy_packages=(),
            native_capabilities=NATIVE_CAPABILITIES,
            safe_mode=True,
        )
        self.assertEqual(outcome.profile.primary_family, "zhipu")
        self.assertNotIn("inbox", outcome.eligible_routes)
        self.assertNotIn("gemini", outcome.eligible_routes)
        self.assertNotIn("codex", outcome.eligible_routes)
        self.assertNotIn("opencode", outcome.eligible_routes)
        self.assertNotIn("grok", outcome.eligible_routes)
        self.assertNotIn("composer", outcome.eligible_routes)
        self.assertIn("safe mode disables native routes", outcome.warning)
        self.assertIn("async inbox is unavailable", outcome.warning)

    def test_inbox_requires_explicit_async_availability_observation(self) -> None:
        base = {
            "primary_id": "custom",
            "active_model": "openai/gpt-5",
            "host_runtime": "custom",
            "session_identifier": "custom-inbox",
        }
        with mock.patch.object(
            self.policy, "_runtime_contracts", return_value=(frozenset(), "")
        ):
            unavailable = self.policy.startup_preflight(
                governance=False,
                explicit_config=base,
                active_legacy_packages=(),
                safe_mode=False,
            )
            observed = self.policy.startup_preflight(
                governance=False,
                explicit_config={**base, "async_inbox": "available"},
                active_legacy_packages=(),
                safe_mode=False,
            )
            bound = self.policy.startup_preflight(
                governance=False,
                explicit_config={**base, "async_inbox": "available"},
                active_legacy_packages=(),
                safe_mode=False,
                async_inbox_target={
                    "target_id": "claude",
                    "target_family": "anthropic",
                    "target_session_identifier": "claude-target-1",
                },
            )
        self.assertNotIn("inbox", unavailable.eligible_routes)
        self.assertIn("async inbox is unavailable", unavailable.warning)
        self.assertNotIn("inbox", observed.eligible_routes)
        self.assertIn("target provenance", observed.warning)
        self.assertIn("inbox", bound.eligible_routes)

    def test_known_host_runtime_is_detected_without_hardcoded_primary_flag(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CODEX_THREAD_ID": "thread-1", "CODEX_ACTIVE_MODEL": "openai/o3"},
            clear=True,
        ):
            profile = self.policy.resolve_profile(None)
        self.assertEqual(profile.primary_id, "codex")
        self.assertEqual(profile.primary_family, "openai")
        self.assertEqual(profile.host_runtime, "codex")
        self.assertEqual(profile.session_identifier, "thread-1")

    def test_codex_profile_uses_safe_rollout_model_without_env(self) -> None:
        thread_id = "019f7e3d-5fb3-7f03-ba2a-795a2cc0e5ad"
        sessions = self._write_codex_rollout(thread_id=thread_id)
        with mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": thread_id}, clear=True
        ), mock.patch.object(
            self.policy,
            "_codex_sessions_root",
            return_value=sessions,
            create=True,
        ):
            profile = self.policy.resolve_profile(None)

        self.assertEqual(profile.primary_id, "codex")
        self.assertEqual(profile.primary_family, "openai")
        self.assertEqual(profile.active_model, "gpt-5.6-sol")
        self.assertEqual(profile.session_identifier, thread_id)
        self.assertTrue(profile.governance_ready)
        self.assertFalse(profile.identity_conflict)

    def test_codex_rollout_entry_limit_aborts_during_scan(self) -> None:
        # A single oversized sessions directory must not be fully materialized
        # before the entry-limit check: counting is incremental and aborts as
        # soon as the cumulative bound is exceeded (bounded memory / no stall).
        policy = self.policy
        consumed = {"n": 0}

        class _Entry:
            def __init__(self, name: str) -> None:
                self.name = name
                self.path = f"/fake/{name}"

        class _Scan:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                # Far more entries than the (patched) limit; each pull is
                # counted so the test can prove the scan stops early.
                i = 0
                while True:
                    consumed["n"] += 1
                    i += 1
                    yield _Entry(f"e{i}")

        safe_root = self.home / "codex-sessions"
        safe_root.mkdir(parents=True, mode=0o755, exist_ok=True)
        with mock.patch.object(policy, "_CODEX_ROLLOUT_ENTRY_LIMIT", 5), mock.patch.object(
            policy, "_safe_codex_directory", return_value=True
        ), mock.patch.object(
            policy.os, "scandir", return_value=_Scan()
        ):
            with self.assertRaises(ValueError) as ctx:
                policy._codex_rollout_candidates(safe_root, "tid")
        self.assertIn("entry bound", str(ctx.exception))
        # Early abort: consumed at most limit+1, NOT an unbounded drain.
        self.assertLessEqual(consumed["n"], 6)

    def test_codex_profile_fails_closed_on_incomplete_rollout_tail(self) -> None:
        # A complete turn_context(model A) followed by a PARTIAL, non-newline-
        # terminated turn_context(model B) — as a concurrent writer produces
        # mid-append — must NOT resolve the stale preceding model A. It fails
        # closed (active_model "unknown", not governance-ready) so a paused
        # writer cannot yield a stale governance-ready identity.
        thread_id = "019f7e3d-5fb3-7f03-ba2a-795a2cc0e5ad"
        sessions = self.home / "codex-sessions"
        directory = sessions / "2026" / "07" / "19"
        directory.mkdir(parents=True, mode=0o755, exist_ok=True)
        path = directory / f"rollout-2026-07-19T00-00-00-{thread_id}.jsonl"
        complete = (
            {
                "type": "session_meta",
                "payload": {"id": thread_id, "model_provider": "openai"},
            },
            {
                "type": "turn_context",
                "payload": {"model": "gpt-5.6-sol"},
            },
        )
        partial = {"type": "turn_context", "payload": {"model": "openai/o3"}}
        body = (
            "\n".join(
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in complete
            )
            + "\n"
            + json.dumps(partial, sort_keys=True, separators=(",", ":"))
        )  # NOTE: no trailing newline — the tail record is incomplete.
        path.write_text(body, encoding="utf-8")
        path.chmod(0o644)

        with mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": thread_id}, clear=True
        ), mock.patch.object(
            self.policy,
            "_codex_sessions_root",
            return_value=sessions,
            create=True,
        ):
            profile = self.policy.resolve_profile(None)

        self.assertNotEqual(profile.active_model, "gpt-5.6-sol")
        self.assertEqual(profile.active_model, "unknown")
        self.assertFalse(profile.governance_ready)

    def test_codex_profile_rejects_env_rollout_model_conflict(self) -> None:
        thread_id = "019f7e3d-5fb3-7f03-ba2a-795a2cc0e5ad"
        sessions = self._write_codex_rollout(thread_id=thread_id)
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_THREAD_ID": thread_id,
                "CODEX_ACTIVE_MODEL": "openai/o3",
            },
            clear=True,
        ), mock.patch.object(
            self.policy,
            "_codex_sessions_root",
            return_value=sessions,
            create=True,
        ):
            profile = self.policy.resolve_profile(None)

        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)
        self.assertEqual(profile.active_model, "gpt-5.6-sol")

    def test_codex_profile_rejects_rollout_growth_during_model_proof(self) -> None:
        thread_id = "019f7e3d-5fb3-7f03-ba2a-795a2cc0e5ad"
        sessions = self._write_codex_rollout(thread_id=thread_id)
        rollout = next(sessions.rglob(f"*-{thread_id}.jsonl"))
        real_fstat = os.fstat
        calls = 0

        def growing_fstat(fd: int) -> os.stat_result:
            nonlocal calls
            calls += 1
            observed = real_fstat(fd)
            if calls == 2:
                fields = list(observed)
                fields[6] = observed.st_size + 1
                return os.stat_result(fields)
            return observed

        with mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": thread_id}, clear=True
        ), mock.patch.object(
            self.policy,
            "_codex_sessions_root",
            return_value=sessions,
            create=True,
        ), mock.patch.object(
            self.policy.os, "fstat", side_effect=growing_fstat
        ):
            profile = self.policy.resolve_profile(None)

        self.assertEqual(calls, 2)
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)
        self.assertEqual(profile.active_model, "unknown")
        self.assertTrue(rollout.is_file())

    def test_codex_profile_rejects_ambiguous_or_unsafe_rollout(self) -> None:
        thread_ids = {
            "duplicate": "019f7e3d-5fb3-7f03-ba2a-795a2cc0e5ad",
            "writable": "019f7e3d-5fb3-7f03-ba2a-795a2cc0e5ae",
        }
        for failure, thread_id in thread_ids.items():
            with self.subTest(failure=failure):
                sessions = self._write_codex_rollout(thread_id=thread_id)
                matches = list(sessions.rglob(f"*-{thread_id}.jsonl"))
                if failure == "duplicate":
                    self._write_codex_rollout(thread_id=thread_id, day="20")
                else:
                    matches[0].chmod(0o666)
                with mock.patch.dict(
                    os.environ, {"CODEX_THREAD_ID": thread_id}, clear=True
                ), mock.patch.object(
                    self.policy,
                    "_codex_sessions_root",
                    return_value=sessions,
                    create=True,
                ):
                    profile = self.policy.resolve_profile(None)

                try:
                    self.assertTrue(profile.identity_conflict)
                    self.assertFalse(profile.governance_ready)
                    self.assertEqual(profile.active_model, "unknown")
                finally:
                    for path in sorted(
                        sessions.rglob(f"*-{thread_id}.jsonl")
                    ):
                        path.unlink()

    def test_partial_primary_overlay_preserves_observed_host_identity(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CODEX_THREAD_ID": "thread-2", "CODEX_ACTIVE_MODEL": "openai/o3"},
            clear=True,
        ):
            profile = self.policy.resolve_profile(
                {"primary_family": "openai"}
            )
        self.assertEqual(profile.primary_id, "codex")
        self.assertEqual(profile.primary_family, "openai")
        self.assertEqual(profile.active_model, "openai/o3")
        self.assertEqual(profile.host_runtime, "codex")
        self.assertEqual(profile.session_identifier, "thread-2")
        self.assertTrue(profile.governance_ready)
        self.assertFalse(profile.identity_conflict)

    def test_observed_identity_model_and_session_cannot_be_overridden(self) -> None:
        observed = {
            "CODEX_THREAD_ID": "thread-strong",
            "CODEX_ACTIVE_MODEL": "openai/o3",
        }
        conflicts = (
            {"primary_id": "claude"},
            {"primary_family": "google"},
            {"active_model": "openai/gpt-5"},
            {"host_runtime": "custom"},
            {"session_identifier": "different-thread"},
        )
        for explicit in conflicts:
            with self.subTest(explicit=explicit), mock.patch.dict(
                "os.environ", observed, clear=True
            ):
                profile = self.policy.resolve_profile(explicit)
            self.assertTrue(profile.identity_conflict)
            self.assertFalse(profile.governance_ready)
            self.assertEqual(profile.primary_id, "codex")
            self.assertEqual(profile.primary_family, "openai")
            self.assertEqual(profile.active_model, "openai/o3")
            self.assertEqual(profile.host_runtime, "codex")
            self.assertEqual(profile.session_identifier, "thread-strong")

    def test_conflicting_explicit_primary_does_not_inherit_observed_identity(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CODEX_THREAD_ID": "thread-3", "CODEX_ACTIVE_MODEL": "openai/o3"},
            clear=True,
        ):
            profile = self.policy.resolve_profile(
                {
                    "primary_id": "claude",
                    "primary_family": "anthropic",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "claude-explicit",
                }
            )
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)
        self.assertEqual(profile.primary_id, "codex")
        self.assertEqual(profile.primary_family, "openai")
        self.assertEqual(profile.active_model, "openai/o3")
        self.assertEqual(profile.host_runtime, "codex")
        self.assertEqual(profile.session_identifier, "thread-3")

    def test_id_only_explicit_primary_cannot_assert_model_family(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            profile = self.policy.resolve_profile({"primary_id": "codex"})
        self.assertEqual(profile.primary_id, "codex")
        self.assertEqual(profile.primary_family, "unknown")
        self.assertFalse(profile.governance_ready)

    def test_complete_explicit_identity_requires_internal_family_consistency(self) -> None:
        consistent = {
            "primary_id": "custom-openai-host",
            "primary_family": "openai",
            "active_model": "openai/gpt-5",
            "host_runtime": "custom",
            "session_identifier": "custom-complete",
        }
        profile = self.policy.resolve_profile(consistent)
        self.assertTrue(profile.governance_ready)
        self.assertFalse(profile.identity_conflict)

        inconsistent = (
            {**consistent, "primary_family": "google"},
            {
                **consistent,
                "primary_id": "claude",
                "primary_family": "openai",
            },
            {**consistent, "active_model": "custom/opaque-model"},
        )
        for config in inconsistent:
            with self.subTest(config=config):
                profile = self.policy.resolve_profile(config)
            self.assertFalse(profile.governance_ready)

    def test_governance_requires_all_five_trustworthy_primary_fields(self) -> None:
        complete = {
            "primary_id": "custom-openai-host",
            "primary_family": "openai",
            "active_model": "openai/gpt-5",
            "host_runtime": "custom",
            "session_identifier": "custom-governance",
        }
        for missing in (
            "primary_id",
            "active_model",
            "host_runtime",
            "session_identifier",
        ):
            with self.subTest(missing=missing):
                config = dict(complete)
                config.pop(missing)
                outcome = self._preflight(
                    governance=True,
                    explicit_config=config,
                    active_legacy_packages=(),
                    safe_mode=False,
                    artifact_author_model="xai/grok-4.5",
                    artifact_content="artifact",
                )
            self.assertEqual(
                outcome.status, self.policy.PreflightStatus.UNKNOWN_BLOCKED
            )
            self.assertEqual(outcome.eligible_routes, ())

        accepted = self._preflight(
            governance=True,
            explicit_config=complete,
            active_legacy_packages=(),
            safe_mode=False,
            artifact_author_model="xai/grok-4.5",
            artifact_content="artifact",
        )
        self.assertEqual(accepted.status, self.policy.PreflightStatus.OK)

    def test_conflicting_observed_and_explicit_identity_blocks_nongovernance(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "CODEX_THREAD_ID": "thread-conflict",
                "CODEX_ACTIVE_MODEL": "openai/o3",
            },
            clear=True,
        ):
            outcome = self._preflight(
                governance=False,
                explicit_config={"active_model": "openai/gpt-5"},
                active_legacy_packages=(),
                safe_mode=False,
            )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.CONFIG_ERROR)
        self.assertEqual(outcome.eligible_routes, ())
        self.assertIn("conflict", outcome.warning.lower())

    def test_ambient_tool_config_does_not_override_active_host_session(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "CLAUDE_CODE_SESSION_ID": "claude-session",
                "CLAUDE_CODE_MODEL": "anthropic/claude-opus",
                "CODEX_HOME": "/ambient/codex",
                "OPENCODE_CONFIG": "/ambient/opencode",
            },
            clear=True,
        ):
            profile = self.policy.resolve_profile(None)
        self.assertEqual(profile.primary_id, "claude")
        self.assertEqual(profile.primary_family, "anthropic")

        with mock.patch.dict(
            "os.environ", {"OPENCODE_CONFIG": "/ambient/opencode"}, clear=True
        ):
            profile = self.policy.resolve_profile(None)
        self.assertEqual(profile.primary_id, "unknown")

    def test_unknown_governance_fails_closed_and_nongovernance_warns(self) -> None:
        unknown_primary = {
            "primary_id": "custom-host",
            "host_runtime": "custom",
            "session_identifier": "custom-1",
        }
        with mock.patch.object(
            self.policy, "_runtime_contracts", return_value=(frozenset(), "")
        ):
            governance = self.policy.startup_preflight(
                governance=True,
                explicit_config=unknown_primary,
                active_legacy_packages=(),
                safe_mode=False,
            )
            ordinary = self.policy.startup_preflight(
                governance=False,
                explicit_config=unknown_primary,
                active_legacy_packages=(),
                safe_mode=False,
            )
        self.assertEqual(governance.status, self.policy.PreflightStatus.UNKNOWN_BLOCKED)
        self.assertEqual(governance.eligible_routes, ())
        self.assertEqual(ordinary.status, self.policy.PreflightStatus.OK)
        self.assertIn("independence warning", ordinary.warning)
        self.assertIn("async inbox is unavailable", ordinary.warning)
        self.assertEqual(ordinary.eligible_routes, ())

        safe = self.policy.startup_preflight(
            governance=False,
            explicit_config=unknown_primary,
            active_legacy_packages=(),
            safe_mode=True,
        )
        self.assertEqual(safe.status, self.policy.PreflightStatus.OK)
        self.assertIn("independence warning", safe.warning)

    def test_doctor_prints_exact_replacement_actions(self) -> None:
        legacy = self.home / ".claude" / "plugins" / "glm-worker"
        legacy.mkdir(parents=True)
        report = self.doctor.build_report(
            home=self.home,
            explicit_config={
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
        )
        rendered = self.doctor.render_report(report)
        self.assertIn("/plugin install agent-collab@agent-collab", rendered)
        self.assertIn("/agent-collab:migration-doctor", rendered)
        self.assertIn(
            "claude plugin uninstall -s user -y glm-worker@agent-collab",
            rendered,
        )
        self.assertIn("PROVIDER ROUTING: BLOCKED", rendered)

    def test_doctor_never_reports_ready_without_native_runtime(self) -> None:
        report = self.doctor.build_report(
            home=self.home,
            explicit_config={
                "primary_id": "codex",
                "active_model": "openai/codex",
                "host_runtime": "codex",
                "session_identifier": "thread-1",
            },
        )
        self.assertEqual(report.native_runtime, "typed unavailable")
        self.assertEqual(report.provider_routing, "BLOCKED")
        self.assertTrue(
            any(
                action == "INSTALL: codex plugin add agent-collab@agent-collab"
                for action in report.actions
            )
        )
        self.assertNotIn("codex plugin install", "\n".join(report.actions))

    def test_doctor_never_reports_ready_when_broker_status_is_unproven(self) -> None:
        with mock.patch.object(
            self.doctor, "_runtime_state", return_value="available"
        ), mock.patch.object(
            self.doctor,
            "_broker_runtime_state",
            return_value="integrity_error",
            create=True,
        ):
            report = self.doctor.build_report(
                home=self.home,
                explicit_config={
                    "primary_id": "codex",
                    "active_model": "openai/codex",
                    "host_runtime": "codex",
                    "session_identifier": "thread-1",
                },
            )

        self.assertEqual(report.native_runtime, "available")
        self.assertEqual(report.broker_runtime, "integrity_error")
        self.assertEqual(report.provider_routing, "BLOCKED")

    def test_doctor_inventories_codex_config_with_observed_host_provenance(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
[plugins."codex-collab@agent-collab"]
enabled = true

[plugins."glm-worker@agent-collab"]
enabled = false

[plugins."agent-collab@agent-collab"]
enabled = true
""".strip()
            + "\n",
            encoding="utf-8",
        )
        inventory = self.doctor.inventory_legacy_packages(self.home)
        self.assertIn("codex-collab", inventory.active_packages)
        self.assertTrue(hasattr(inventory, "installed_packages"))
        self.assertTrue(hasattr(inventory, "observations"))
        self.assertEqual(
            set(inventory.installed_packages), {"codex-collab", "glm-worker"}
        )
        observed = {
            (item.package, item.host_runtime, item.state)
            for item in inventory.observations
        }
        self.assertIn(("codex-collab", "codex", "enabled"), observed)
        self.assertIn(("glm-worker", "codex", "installed-disabled"), observed)

        report = self.doctor.build_report(
            home=self.home,
            explicit_config={
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-doctor",
            },
        )
        rendered = self.doctor.render_report(report)
        self.assertEqual(report.host_profile["host_runtime"], "claude-code")
        self.assertIn("codex plugin remove codex-collab@agent-collab --json", rendered)
        self.assertIn("codex plugin remove glm-worker@agent-collab --json", rendered)
        self.assertNotIn(
            "claude plugin uninstall -s user -y codex-collab@agent-collab",
            rendered,
        )
        self.assertIn("codex / installed-disabled / glm-worker", rendered)

    def test_doctor_uses_neutral_manual_actions_for_non_cli_hosts(self) -> None:
        for host in ("antigravity", "opencode", "custom"):
            with self.subTest(host=host):
                report = self.doctor.build_report(
                    home=self.home,
                    explicit_config={
                        "primary_id": host,
                        "active_model": "custom/unknown",
                        "host_runtime": host,
                        "session_identifier": "s-1",
                    },
                )
                self.assertTrue(report.actions[0].startswith("MANUAL:"))
                self.assertNotIn("claude plugin", "\n".join(report.actions))

    def test_every_primary_family_is_excluded_from_all_route_classes(self) -> None:
        cases = {
            "anthropic": {"inbox"},
            "google": {"gemini"},
            "openai": {"codex"},
            "xai": {"grok", "composer"},
            "zhipu": {"opencode"},
        }
        all_routes = {"inbox", "gemini", "codex", "opencode", "grok", "composer"}
        for family, excluded in cases.items():
            with self.subTest(family=family):
                outcome = self._preflight(
                    governance=False,
                    explicit_config={
                        "primary_id": f"primary-{family}",
                        "primary_family": family,
                        "active_model": f"model-{family}",
                        "host_runtime": "custom",
                        "session_identifier": f"session-{family}",
                        "async_inbox": "available",
                    },
                    active_legacy_packages=(),
                    native_capabilities=NATIVE_CAPABILITIES,
                    safe_mode=False,
                    route_models={"opencode": "opencode/glm-5.2"},
                    async_inbox_target=(
                        None
                        if family == "anthropic"
                        else {
                            "target_id": "claude",
                            "target_family": "anthropic",
                            "target_session_identifier": "claude-route-matrix",
                        }
                    ),
                )
                self.assertTrue(excluded.isdisjoint(outcome.eligible_routes))
                self.assertTrue((all_routes - excluded).issubset(outcome.eligible_routes))

    def test_zcode_glm_keeps_independent_gemini_grok_codex_paths(self) -> None:
        outcome = self._preflight(
            governance=True,
            explicit_config={
                "primary_id": "zcode",
                "active_model": "opencode/glm-5.2",
                "host_runtime": "opencode",
                "session_identifier": "z-1",
            },
            active_legacy_packages=(),
            native_capabilities=NATIVE_CAPABILITIES,
            safe_mode=False,
            artifact_author_model="opencode/glm-5.2",
            artifact_content="draft",
        )
        self.assertEqual(outcome.profile.primary_family, "zhipu")
        self.assertIn("gemini", outcome.eligible_routes)
        self.assertIn("grok", outcome.eligible_routes)
        self.assertIn("codex", outcome.eligible_routes)
        self.assertNotIn("opencode", outcome.eligible_routes)
        self.assertNotIn("composer", outcome.eligible_routes)

    def test_opencode_model_family_is_dynamic_and_not_runtime_identity(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "ZCODE_SESSION_ID": "z-switch",
                "OPENCODE_CONFIG": "/tmp/config",
                "OPENCODE_ACTIVE_MODEL": "opencode/glm-5.2",
            },
            clear=True,
        ):
            before = self.policy.resolve_profile(None)
        with mock.patch.dict(
            "os.environ",
            {
                "ZCODE_SESSION_ID": "z-switch",
                "OPENCODE_CONFIG": "/tmp/config",
                "OPENCODE_ACTIVE_MODEL": "google/gemini-2.5-pro",
            },
            clear=True,
        ):
            after = self.policy.resolve_profile(None)
        self.assertEqual(before.primary_family, "zhipu")
        self.assertEqual(after.primary_family, "google")
        self.assertEqual(after.host_runtime, "opencode")

    def test_model_family_resolution_covers_every_supported_family(self) -> None:
        cases = {
            "anthropic/claude-opus": "anthropic",
            "google/gemini-pro": "google",
            "openai/codex": "openai",
            "xai/grok-4.5": "xai",
            "xai/composer": "xai",
            "opencode/glm-5.2": "zhipu",
            "custom/undisclosed": "unknown",
        }
        for model, expected in cases.items():
            with self.subTest(model=model):
                self.assertEqual(self.policy.resolve_model_family(model), expected)

    def test_model_family_resolution_fails_closed_on_ambiguous_or_substring_ids(self) -> None:
        cases = (
            "openai/google/gemini-pro",
            "google/openai/codex",
            "anthropic/grok-4.5",
            "xai/claude-opus",
            "opencode/openai/gemini-pro",
            "custom/notopenai-model",
            "custom/superclaudeish",
        )
        for model in cases:
            with self.subTest(model=model):
                self.assertEqual(self.policy.resolve_model_family(model), "unknown")

    def test_artifact_author_family_is_also_excluded(self) -> None:
        outcome = self._preflight(
            governance=True,
            explicit_config={
                "primary_id": "claude",
                "primary_family": "anthropic",
                "active_model": "claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
            artifact_author_model="xai/grok-4.5",
            artifact_content="draft",
            active_legacy_packages=(),
            native_capabilities=NATIVE_CAPABILITIES,
            safe_mode=False,
        )
        self.assertNotIn("inbox", outcome.eligible_routes)
        self.assertNotIn("grok", outcome.eligible_routes)
        self.assertNotIn("composer", outcome.eligible_routes)

    def test_non_governance_worker_excludes_optional_artifact_author_family(self) -> None:
        cases = (
            (
                "opencode",
                "build",
                {"cwd": "/tmp/work", "model": "opencode/glm-5.2"},
                "zhipu/glm-5.2",
            ),
            (
                "composer",
                "codegen",
                {"task_class": "standard_codegen", "effort": "medium"},
                "xai/composer",
            ),
        )
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(
                frozenset((route, action) for route, action, _, _ in cases),
                "digest-1",
            ),
        ):
            for route, action, row, artifact_model in cases:
                with self.subTest(route=route, action=action):
                    outcome = self.policy.issue_policy_envelope(
                        request_id=f"worker-artifact-{route}",
                        route=route,
                        action=action,
                        governance=False,
                        prompt="generate",
                        timeout_ms=30_000,
                        explicit_config={
                            "primary_id": "claude",
                            "active_model": "anthropic/claude-opus",
                            "host_runtime": "claude-code",
                            "session_identifier": "c-worker",
                        },
                        row_config=row,
                        artifact_author_model=artifact_model,
                        artifact_content="existing implementation",
                    )
                    self.assertEqual(
                        outcome.status, self.policy.PreflightStatus.SAME_FAMILY_BLOCKED
                    )
                    self.assertIsNone(outcome.envelope)

    def test_unknown_optional_worker_artifact_emits_independence_warning(self) -> None:
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("composer", "codegen")}), "digest-1"),
        ):
            outcome = self.policy.issue_policy_envelope(
                request_id="worker-unknown-artifact",
                route="composer",
                action="codegen",
                governance=False,
                prompt="generate",
                timeout_ms=30_000,
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-worker-unknown",
                },
                row_config={"task_class": "standard_codegen", "effort": "medium"},
                artifact_author_model="custom/opaque-model",
                artifact_content="existing implementation",
            )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        self.assertIsNotNone(outcome.envelope)
        self.assertIn("unknown artifact-author family", outcome.warning)

    def test_open_code_claude_model_is_never_an_autonomous_route(self) -> None:
        outcome = self._preflight(
            governance=False,
            explicit_config={
                "primary_id": "custom",
                "primary_family": "openai",
                "active_model": "openai/gpt-5",
                "host_runtime": "custom",
                "session_identifier": "custom-1",
                "opencode_model": "anthropic/claude-sonnet",
            },
            active_legacy_packages=(),
            native_capabilities=NATIVE_CAPABILITIES,
            safe_mode=False,
        )
        self.assertNotIn("opencode", outcome.eligible_routes)

    def test_opencode_preflight_matches_issuance_default_and_ignores_ambient_rows(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"AGENT_COLLAB_OPENCODE_MODEL": "anthropic/claude-ambient"},
            clear=True,
        ):
            outcome = self._preflight(
                governance=False,
                explicit_config={
                    "primary_id": "custom",
                    "primary_family": "openai",
                    "active_model": "openai/gpt-5",
                    "host_runtime": "custom",
                    "session_identifier": "custom-default-1",
                },
                active_legacy_packages=(),
                native_capabilities=NATIVE_CAPABILITIES,
                safe_mode=False,
                route_models={"opencode": "anthropic/claude-row"},
            )

        self.assertIn("opencode", outcome.eligible_routes)
        self.assertNotIn("OpenCode model is not currently observed", outcome.warning)

    def test_explicit_model_family_conflicts_are_never_governance_trusted(self) -> None:
        cases = {
            "anthropic/claude-opus": "anthropic",
            "google/gemini-2.5-pro": "google",
            "openai/codex": "openai",
            "xai/grok-4.5": "xai",
            "opencode/glm-5.2": "zhipu",
        }
        for model, expected in cases.items():
            with self.subTest(model=model):
                profile = self.policy.resolve_profile(
                    {
                        "primary_id": "zcode",
                        "primary_family": "openai",
                        "active_model": model,
                        "host_runtime": "opencode",
                        "session_identifier": "switch-1",
                    }
                )
                self.assertEqual(profile.primary_family, expected)
                self.assertEqual(profile.identity_conflict, expected != "openai")
                self.assertEqual(profile.governance_ready, expected == "openai")

        unknown_model = self.policy.resolve_profile(
            {
                "primary_id": "zcode",
                "primary_family": "openai",
                "active_model": "custom/unknown-model",
                "host_runtime": "opencode",
                "session_identifier": "switch-1",
            }
        )
        self.assertEqual(unknown_model.primary_family, "openai")
        self.assertFalse(unknown_model.identity_conflict)
        self.assertFalse(unknown_model.governance_ready)

    def test_ambiguous_active_model_never_falls_back_to_asserted_family(self) -> None:
        config = {
            "primary_id": "zcode",
            "primary_family": "openai",
            "active_model": "openai/google/gemini-pro",
            "host_runtime": "opencode",
            "session_identifier": "ambiguous-1",
        }
        profile = self.policy.resolve_profile(config)
        self.assertEqual(profile.primary_family, "unknown")
        outcome = self._preflight(
            governance=True,
            explicit_config=config,
            active_legacy_packages=(),
            safe_mode=False,
            artifact_author_model="xai/grok-4.5",
            artifact_content="artifact",
        )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.CONFIG_ERROR)
        self.assertEqual(outcome.eligible_routes, ())

    def test_empty_runtime_manifest_cannot_be_made_ready_by_capability_assertion(self) -> None:
        with mock.patch.object(
            self.policy,
            "PLUGIN_ROOT",
            PLUGIN,
        ):
            outcome = self.policy.startup_preflight(
                governance=False,
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-empty",
                },
                active_legacy_packages=(),
                native_capabilities=NATIVE_CAPABILITIES,
                safe_mode=False,
                route_models={"opencode": "opencode/glm-5.2"},
            )
        self.assertEqual(outcome.eligible_routes, ())
        self.assertIn("typed unavailable", outcome.warning)

    def test_governance_requires_captured_artifact_model_not_family_assertion(self) -> None:
        with self.assertRaises(TypeError):
            self.policy.issue_policy_envelope(
                request_id="governance-1",
                route="codex",
                action="advisory",
                governance=True,
                prompt="review",
                timeout_ms=30_000,
                artifact_author_family="google",
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-1",
                },
            )

        outcome = self.policy.issue_policy_envelope(
            request_id="governance-2",
            route="codex",
            action="advisory",
            governance=True,
            prompt="review",
            timeout_ms=30_000,
            artifact_author_model="",
            artifact_content="draft",
            explicit_config={
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
        )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.UNKNOWN_BLOCKED)
        self.assertIsNone(outcome.envelope)

    def test_governance_rejects_model_without_artifact_bytes(self) -> None:
        outcome = self.policy.issue_policy_envelope(
            request_id="governance-empty",
            route="grok",
            action="governance",
            governance=True,
            prompt="review",
            timeout_ms=30_000,
            row_config={"mode": "prompt-only"},
            artifact_author_model="google/gemini-test",
            artifact_content="",
            explicit_config={
                "primary_id": "codex",
                "active_model": "openai/gpt-5",
                "host_runtime": "codex",
                "session_identifier": "c-empty",
            },
        )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.CONFIG_ERROR)
        self.assertIsNone(outcome.envelope)

    def test_artifact_presence_depends_on_nonblank_captured_bytes(self) -> None:
        missing = self.policy._capture_artifact(
            " \n\t", "google/gemini-test"
        )
        unknown_lineage = self.policy._capture_artifact("material", "  ")

        self.assertFalse(missing.present)
        self.assertTrue(unknown_lineage.present)
        self.assertEqual(unknown_lineage.author_family, "unknown")

    def test_startup_preflight_rejects_model_without_artifact_bytes(self) -> None:
        outcome = self.policy.startup_preflight(
            governance=False,
            explicit_config={
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "preflight-empty",
            },
            active_legacy_packages=(),
            safe_mode=False,
            artifact_author_model="google/gemini-test",
            artifact_content=" \n\t",
        )

        self.assertEqual(outcome.status, self.policy.PreflightStatus.CONFIG_ERROR)
        self.assertEqual(outcome.eligible_routes, ())
        self.assertIn("artifact", outcome.warning)

    def test_non_governance_rejects_model_without_artifact_bytes(self) -> None:
        outcome = self.policy.issue_policy_envelope(
            request_id="optional-empty",
            route="composer",
            action="codegen",
            governance=False,
            prompt="generate",
            timeout_ms=30_000,
            row_config={"task_class": "standard_codegen", "effort": "medium"},
            artifact_author_model="google/gemini-test",
            artifact_content=" \n\t",
            explicit_config={
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "optional-empty",
            },
        )

        self.assertEqual(outcome.status, self.policy.PreflightStatus.CONFIG_ERROR)
        self.assertIsNone(outcome.envelope)

    def test_non_governance_nonblank_artifact_with_blank_lineage_warns(self) -> None:
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("composer", "codegen")}), "digest-1"),
        ):
            outcome = self.policy.issue_policy_envelope(
                request_id="optional-unknown-lineage",
                route="composer",
                action="codegen",
                governance=False,
                prompt="generate",
                timeout_ms=30_000,
                row_config={"task_class": "standard_codegen", "effort": "medium"},
                artifact_author_model="  ",
                artifact_content="existing implementation",
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "optional-unknown-lineage",
                },
            )

        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        self.assertIsNotNone(outcome.envelope)
        assert outcome.envelope is not None
        self.assertTrue(outcome.envelope.artifact_present)
        self.assertIn("unknown artifact-author family", outcome.warning)

    def test_grok_review_rows_are_sealed_to_role_task_and_effort(self) -> None:
        profile = self.policy.resolve_profile(
            {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "grok-review-seal",
            }
        )
        cases = (
            (
                ("grok", "architecture"),
                {"mode": "prompt-only"},
                {"mode": "prompt-only", "task_class": "architecture", "effort": "high"},
            ),
            (
                ("grok", "governance"),
                {"mode": "prompt-only"},
                {"mode": "prompt-only", "task_class": "governance", "effort": "high"},
            ),
            (
                ("grok", "huge_context"),
                {"documents": [{"label": "a", "content": "document"}]},
                {
                    "documents": [{"label": "a", "content": "document"}],
                    "task_class": "huge_context",
                    "effort": "medium",
                },
            ),
        )
        for (route, action), row, expected in cases:
            with self.subTest(action=action):
                validated, family, error = self.policy._validate_row(
                    route, action, row, profile, {}
                )
                self.assertEqual(error, "")
                self.assertEqual(family, "xai")
                self.assertEqual(validated, expected)

        for forbidden in (
            {"mode": "prompt-only", "effort": "low"},
            {"mode": "prompt-only", "task_class": "simple_codegen"},
            {"mode": "prompt-only", "model": "xai/grok-4.5"},
        ):
            with self.subTest(forbidden=forbidden):
                validated, _family, _error = self.policy._validate_row(
                    "grok", "architecture", forbidden, profile, {}
                )
                self.assertIsNone(validated)

    def test_composer_compatibility_route_enforces_codegen_effort_floors(self) -> None:
        profile = self.policy.resolve_profile(
            {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "grok-codegen-seal",
            }
        )
        accepted = (
            ("simple_codegen", "low"),
            ("simple_codegen", "high"),
            ("standard_codegen", "medium"),
            ("standard_codegen", "high"),
            ("complex_codegen", "high"),
        )
        for task_class, effort in accepted:
            with self.subTest(task_class=task_class, effort=effort):
                row = {"task_class": task_class, "effort": effort}
                validated, family, error = self.policy._validate_row(
                    "composer", "codegen", row, profile, {}
                )
                self.assertEqual((validated, family, error), (row, "xai", ""))

        rejected = (
            {},
            {"task_class": "standard_codegen", "effort": "low"},
            {"task_class": "complex_codegen", "effort": "medium"},
            {"task_class": "simple_codegen", "effort": "xhigh"},
            {
                "task_class": "simple_codegen",
                "effort": "low",
                "model": "xai/grok-4.5",
            },
        )
        for row in rejected:
            with self.subTest(row=row):
                validated, _family, _error = self.policy._validate_row(
                    "composer", "codegen", row, profile, {}
                )
                self.assertIsNone(validated)

    def test_policy_envelope_detects_tampering(self) -> None:
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("codex", "advisory")}), "digest-1"),
        ):
            outcome = self.policy.issue_policy_envelope(
                request_id="sealed-1",
                route="codex",
                action="advisory",
                governance=True,
                prompt="review",
                timeout_ms=30_000,
                artifact_author_model="google/gemini-2.5-pro",
                artifact_content="draft",
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-1",
                },
                row_config={"model": "openai/codex", "effort": "high", "mode": "prompt-only"},
            )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        self.assertIsNotNone(outcome.envelope)
        assert outcome.envelope is not None
        self.assertTrue(self.policy.verify_policy_envelope(outcome.envelope))
        tampered = dataclasses.replace(outcome.envelope, action="build")
        self.assertFalse(self.policy.verify_policy_envelope(tampered))

    def test_policy_envelope_preserves_automatic_target_provenance(self) -> None:
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("codex", "advisory")}), "digest-1"),
        ):
            outcome = self.policy.issue_policy_envelope(
                request_id="automatic-1",
                route="codex",
                action="advisory",
                governance=False,
                prompt="review",
                timeout_ms=30_000,
                explicit_target=False,
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-1",
                },
                row_config={
                    "model": "openai/codex",
                    "effort": "high",
                    "mode": "prompt-only",
                },
            )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        self.assertIsNotNone(outcome.envelope)
        assert outcome.envelope is not None
        self.assertFalse(outcome.envelope.explicit_target)
        self.assertTrue(self.policy.verify_policy_envelope(outcome.envelope))

    def test_opencode_target_uses_the_fixed_glm_preset_by_default(self) -> None:
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("opencode", "plan")}), "digest-1"),
        ):
            outcome = self.policy.issue_policy_envelope(
                request_id="opencode-no-model",
                route="opencode",
                action="plan",
                governance=False,
                prompt="plan",
                timeout_ms=30_000,
                explicit_config={
                    "primary_id": "custom",
                    "active_model": "openai/gpt-5",
                    "host_runtime": "custom",
                    "session_identifier": "custom-1",
                },
                row_config={"cwd": "/tmp/project"},
            )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        self.assertIsNotNone(outcome.envelope)
        assert outcome.envelope is not None
        row = json.loads(outcome.envelope.row_json)
        self.assertEqual(row["model"], self.policy.DEFAULT_OPENCODE_MODEL)
        self.assertEqual(outcome.envelope.target_author_family, "zhipu")

    def test_opencode_ignores_ambient_and_row_model_fallbacks(self) -> None:
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("opencode", "plan")}), "digest-1"),
        ), mock.patch.dict(
            "os.environ",
            {"AGENT_COLLAB_OPENCODE_MODEL": "google/gemini-ambient"},
            clear=True,
        ):
            outcome = self.policy.issue_policy_envelope(
                request_id="opencode-closed-precedence",
                route="opencode",
                action="plan",
                governance=False,
                prompt="plan",
                timeout_ms=30_000,
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-1",
                },
                row_config={"model": "openai/row-model", "cwd": "/tmp/project"},
            )
        self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
        assert outcome.envelope is not None
        self.assertEqual(
            json.loads(outcome.envelope.row_json)["model"],
            self.policy.DEFAULT_OPENCODE_MODEL,
        )

    def test_opencode_worker_reobserves_explicit_selected_model_on_each_call(self) -> None:
        cases = {
            "google/gemini-2.5-pro": "google",
            "openai/gpt-5": "openai",
            "xai/grok-4.5": "xai",
            "opencode/glm-5.2": "zhipu",
        }
        with mock.patch.object(
            self.policy,
            "_runtime_contracts",
            return_value=(frozenset({("opencode", "plan")}), "digest-1"),
        ):
            for model, family in cases.items():
                with self.subTest(model=model):
                    outcome = self.policy.issue_policy_envelope(
                        request_id=f"switch-{family}",
                        route="opencode",
                        action="plan",
                        governance=False,
                        prompt="plan",
                        timeout_ms=30_000,
                        explicit_config={
                            "primary_id": "claude",
                            "active_model": "anthropic/claude-opus",
                            "host_runtime": "claude-code",
                            "session_identifier": "c-1",
                            "opencode_model": model,
                        },
                        row_config={
                            "model": "opencode/glm-stale",
                            "cwd": "/tmp/project",
                        },
                    )
                    self.assertEqual(outcome.status, self.policy.PreflightStatus.OK)
                    assert outcome.envelope is not None
                    self.assertEqual(outcome.envelope.target_author_family, family)
                    self.assertEqual(
                        json.loads(outcome.envelope.row_json)["model"],
                        model,
                    )

            for model, expected in (
                ("anthropic/claude-sonnet", self.policy.PreflightStatus.CONFIG_ERROR),
                ("custom/undisclosed", self.policy.PreflightStatus.UNKNOWN_BLOCKED),
            ):
                with self.subTest(model=model):
                    outcome = self.policy.issue_policy_envelope(
                        request_id="switch-denied",
                        route="opencode",
                        action="plan",
                        governance=False,
                        prompt="plan",
                        timeout_ms=30_000,
                        explicit_config={
                            "primary_id": "codex",
                            "active_model": "openai/codex",
                            "host_runtime": "codex",
                            "session_identifier": "o-1",
                            "opencode_model": model,
                        },
                        row_config={"cwd": "/tmp/project"},
                    )
                    self.assertEqual(outcome.status, expected)


if __name__ == "__main__":
    unittest.main()
