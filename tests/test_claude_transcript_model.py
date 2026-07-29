"""Bounded observation of the live Claude session model from its transcript.

Claude Code does not export the active model to the environment, so before this
observation existed a Claude host resolved ``active_model='unknown'`` and every
governance route failed closed with ``unknown_family``. Callers then hand-filled
``primary``, fabricated ``session_identifier`` (which a caller cannot know), and
tripped the identity-conflict guard.

These tests pin the mechanism AND its fail-closed posture. The observation is
same-uid best-effort anti-confusion, not a forgery-resistant attestation.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"

SESSION = "07a2aa37-f15c-4604-a184-d969ef9d01ac"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


host_policy = _load("claude_transcript_host_policy", PLUGIN / "host_policy.py")


def _assistant(model: str, *, session: str = SESSION, sidechain=False) -> str:
    record = {
        "type": "assistant",
        "sessionId": session,
        "isSidechain": sidechain,
        "message": {"role": "assistant", "model": model},
    }
    return json.dumps(record) + "\n"


class ClaudeTranscriptModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.projects = self.home / ".claude" / "projects"
        self.projects.mkdir(parents=True)
        os.chmod(self.projects, 0o700)
        self.addCleanup(self._tmp.cleanup)

    def _project(self, name: str = "-Users-x-repo") -> Path:
        path = self.projects / name
        path.mkdir(exist_ok=True)
        os.chmod(path, 0o700)
        return path

    def _write(self, body: str, *, project: str = "-Users-x-repo", session: str = SESSION) -> Path:
        path = self._project(project) / f"{session}.jsonl"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o600)
        return path

    def _resolve(self, session: str = SESSION):
        with mock.patch.object(
            host_policy, "_claude_projects_root", return_value=self.projects
        ):
            return host_policy._claude_transcript_model(session)

    # -- happy path ----------------------------------------------------------

    def test_resolves_newest_assistant_model(self):
        self._write(_assistant("claude-sonnet-5") + _assistant("claude-opus-5"))
        self.assertEqual(self._resolve(), ("ok", "claude-opus-5"))

    def test_unreleased_model_name_resolves_without_an_allowlist(self):
        """No pinned model list: a future model must work with no code edit."""
        self._write(_assistant("claude-nextgen-9-20990101"))
        self.assertEqual(self._resolve(), ("ok", "claude-nextgen-9-20990101"))

    # -- sentinel and non-qualifying records ---------------------------------

    def test_synthetic_sentinel_is_skipped_not_accepted(self):
        self._write(_assistant("claude-opus-5") + _assistant("<synthetic>"))
        self.assertEqual(self._resolve(), ("ok", "claude-opus-5"))

    def test_sidechain_record_is_skipped(self):
        self._write(_assistant("claude-opus-5") + _assistant("claude-haiku-4-5", sidechain=True))
        self.assertEqual(self._resolve(), ("ok", "claude-opus-5"))

    def test_non_bool_sidechain_flag_fails_closed(self):
        self._write(_assistant("claude-opus-5").replace('"isSidechain": false', '"isSidechain": "true"'))
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_no_assistant_record_is_absent_not_invalid(self):
        self._write(json.dumps({"type": "user", "sessionId": SESSION}) + "\n")
        self.assertEqual(self._resolve(), ("absent", ""))

    # -- family binding: the load-bearing bypass defence ---------------------

    def test_cross_family_model_fails_closed_and_cannot_reassign_family(self):
        """A forged cross-family record must not become an OpenAI primary."""
        self._write(_assistant("claude-opus-5") + _assistant("gpt-4o"))
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_google_and_xai_model_claims_also_fail_closed(self):
        for model in ("gemini-3.1-pro", "grok-4.5", "glm-5.2"):
            with self.subTest(model=model):
                self._write(_assistant(model))
                self.assertEqual(self._resolve(), ("invalid", ""))

    def test_oversized_model_string_fails_closed(self):
        self._write(_assistant("claude-" + "a" * 200))
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_session_id_mismatch_inside_record_fails_closed(self):
        self._write(_assistant("claude-opus-5", session="ffffffff-0000-0000-0000-000000000000"))
        self.assertEqual(self._resolve(), ("invalid", ""))

    # -- path and identity hardening -----------------------------------------

    def test_empty_session_id_is_absent(self):
        self.assertEqual(self._resolve(""), ("absent", ""))

    def test_malformed_session_id_fails_closed_rather_than_reading_absent(self):
        """A nonempty non-UUID id still reaches the profile, so it must conflict."""
        for bad in (
            "../../etc/passwd",
            "*",
            "07A2AA37-F15C-4604-A184-D969EF9D01AC",
            "a/b",
            "not-a-uuid-at-all",
        ):
            with self.subTest(session=bad):
                self.assertEqual(self._resolve(bad), ("invalid", ""))

    def test_missing_transcript_is_absent(self):
        self._project()
        self.assertEqual(self._resolve(), ("absent", ""))

    def test_ambiguous_duplicate_across_projects_fails_closed(self):
        self._write(_assistant("claude-opus-5"), project="-Users-x-repo")
        self._write(_assistant("claude-sonnet-5"), project="-Users-x-other")
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_symlinked_transcript_is_rejected(self):
        real = self.home / "planted.jsonl"
        real.write_text(_assistant("claude-opus-5"), encoding="utf-8")
        os.chmod(real, 0o600)
        os.symlink(real, self._project() / f"{SESSION}.jsonl")
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_group_writable_transcript_is_rejected(self):
        path = self._write(_assistant("claude-opus-5"))
        os.chmod(path, 0o620)
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_hardlinked_transcript_is_rejected(self):
        path = self._write(_assistant("claude-opus-5"))
        os.link(path, self.home / "second-link.jsonl")
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_symlinked_project_directory_is_skipped_not_followed(self):
        outside = self.home / "attacker"
        outside.mkdir()
        os.chmod(outside, 0o700)
        planted = outside / f"{SESSION}.jsonl"
        planted.write_text(_assistant("gpt-4o"), encoding="utf-8")
        os.chmod(planted, 0o600)
        os.symlink(outside, self.projects / "-evil")
        self.assertEqual(self._resolve(), ("absent", ""))

    def test_group_writable_project_directory_is_skipped(self):
        self._write(_assistant("claude-opus-5"), project="-Users-x-repo")
        loose = self.projects / "-loose"
        loose.mkdir()
        os.chmod(loose, 0o777)
        # The loose directory is skipped; the well-formed one still resolves.
        self.assertEqual(self._resolve(), ("ok", "claude-opus-5"))

    def test_malformed_json_fails_closed(self):
        self._write("{not json at all\n")
        self.assertEqual(self._resolve(), ("invalid", ""))

    def test_incomplete_final_line_fails_closed(self):
        self._write(_assistant("claude-opus-5").rstrip("\n"))
        self.assertEqual(self._resolve(), ("invalid", ""))


class ClaudeProfileWiringTests(unittest.TestCase):
    """The observation must reach resolve_profile with the Codex state contract."""

    def _profile(self, state, model, env=None):
        environ = {"CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_CODE_ENTRYPOINT": "cli"}
        environ.update(env or {})
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(
            host_policy, "_claude_transcript_model", return_value=(state, model)
        ):
            return host_policy.resolve_profile(None)

    def test_observed_model_makes_a_claude_host_governance_ready(self):
        profile = self._profile("ok", "claude-opus-5")
        self.assertEqual(profile.active_model, "claude-opus-5")
        self.assertEqual(profile.primary_family, "anthropic")
        self.assertFalse(profile.identity_conflict)
        self.assertTrue(profile.governance_ready)

    def test_invalid_observation_is_unknown_and_conflicting(self):
        profile = self._profile("invalid", "")
        self.assertEqual(profile.active_model, "unknown")
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_absent_observation_preserves_prior_environment_behaviour(self):
        profile = self._profile("absent", "")
        self.assertEqual(profile.active_model, "unknown")
        self.assertFalse(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_environment_model_agreeing_with_observation_is_not_a_conflict(self):
        profile = self._profile("ok", "claude-opus-5", {"CLAUDE_CODE_MODEL": "Claude-Opus-5"})
        self.assertFalse(profile.identity_conflict)

    def test_environment_model_disagreeing_with_observation_conflicts(self):
        profile = self._profile("ok", "claude-opus-5", {"CLAUDE_CODE_MODEL": "claude-sonnet-5"})
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_explicit_caller_model_disagreeing_with_observation_conflicts(self):
        """A hand-authored `primary` cannot override strong observation."""
        environ = {"CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_CODE_ENTRYPOINT": "cli"}
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(
            host_policy, "_claude_transcript_model", return_value=("ok", "claude-opus-5")
        ):
            profile = host_policy.resolve_profile({"active_model": "claude-sonnet-5"})
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_fabricated_session_identifier_still_conflicts(self):
        """The original defect: a caller-invented session id is never an override."""
        environ = {"CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_CODE_ENTRYPOINT": "cli"}
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(
            host_policy, "_claude_transcript_model", return_value=("ok", "claude-opus-5")
        ):
            profile = host_policy.resolve_profile(
                {"session_identifier": "11111111-1111-1111-1111-111111111111"}
            )
        self.assertEqual(profile.session_identifier, SESSION)
        self.assertTrue(profile.identity_conflict)


class ClaudeUnfillableIdentityTests(unittest.TestCase):
    """An unobserved Claude session must not be made governance-ready by config.

    These exercise `resolve_profile` end to end against real files, WITHOUT
    mocking `_claude_transcript_model`, so they prove the state labels cannot be
    manoeuvred into eligibility rather than merely restating the wiring.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.projects = self.home / ".claude" / "projects"
        self.projects.mkdir(parents=True)
        os.chmod(self.projects, 0o700)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, body: str, *, session: str = SESSION) -> None:
        project = self.projects / "-Users-x-repo"
        project.mkdir(exist_ok=True)
        os.chmod(project, 0o700)
        path = project / f"{session}.jsonl"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o600)

    def _profile(self, env, explicit=None):
        environ = {"CLAUDE_CODE_ENTRYPOINT": "cli"}
        environ.update(env)
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(
            host_policy, "_claude_projects_root", return_value=self.projects
        ):
            return host_policy.resolve_profile(explicit)

    def test_end_to_end_real_transcript_yields_governance_ready(self):
        self._write(_assistant("claude-opus-5"))
        profile = self._profile({"CLAUDE_CODE_SESSION_ID": SESSION})
        self.assertEqual(profile.active_model, "claude-opus-5")
        self.assertEqual(profile.primary_family, "anthropic")
        self.assertFalse(profile.identity_conflict)
        self.assertTrue(profile.governance_ready)

    def test_absent_transcript_cannot_be_filled_by_environment(self):
        profile = self._profile(
            {
                "CLAUDE_CODE_SESSION_ID": SESSION,
                "AGENT_COLLAB_ACTIVE_MODEL": "claude-opus-5",
            }
        )
        self.assertEqual(profile.active_model, "unknown")
        self.assertFalse(profile.governance_ready)

    def test_absent_transcript_cannot_be_filled_by_explicit_primary(self):
        profile = self._profile(
            {"CLAUDE_CODE_SESSION_ID": SESSION}, {"active_model": "claude-opus-5"}
        )
        self.assertEqual(profile.active_model, "unknown")
        self.assertFalse(profile.governance_ready)

    def test_malformed_session_with_filled_model_is_not_governance_ready(self):
        profile = self._profile(
            {"CLAUDE_CODE_SESSION_ID": "not-a-uuid-at-all"},
            {"active_model": "claude-opus-5"},
        )
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_cross_family_transcript_record_cannot_be_rescued_by_config(self):
        self._write(_assistant("gpt-4o"))
        profile = self._profile(
            {"CLAUDE_CODE_SESSION_ID": SESSION}, {"active_model": "claude-opus-5"}
        )
        self.assertEqual(profile.primary_family, "anthropic")
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_unreadable_transcript_is_not_filled(self):
        self._write(_assistant("claude-opus-5"))
        project = self.projects / "-Users-x-repo"
        os.chmod(project / f"{SESSION}.jsonl", 0o000)
        self.addCleanup(os.chmod, project / f"{SESSION}.jsonl", 0o600)
        profile = self._profile(
            {
                "CLAUDE_CODE_SESSION_ID": SESSION,
                "AGENT_COLLAB_ACTIVE_MODEL": "claude-opus-5",
            }
        )
        self.assertFalse(profile.governance_ready)

    def test_assistant_record_evicted_from_the_bounded_window_is_not_filled(self):
        """Padding the tail past the scan bound must not open an env fill path."""
        limit = host_policy._CODEX_ROLLOUT_SCAN_LIMIT
        filler = json.dumps({"type": "user", "sessionId": SESSION, "pad": "p" * 4096}) + "\n"
        body = _assistant("claude-opus-5") + filler * ((limit // len(filler)) + 2)
        self._write(body)
        profile = self._profile(
            {
                "CLAUDE_CODE_SESSION_ID": SESSION,
                "AGENT_COLLAB_ACTIVE_MODEL": "claude-sonnet-5",
            }
        )
        self.assertEqual(profile.active_model, "unknown")
        self.assertFalse(profile.governance_ready)

    def test_no_session_identifier_leaves_governance_closed(self):
        profile = self._profile({"AGENT_COLLAB_ACTIVE_MODEL": "claude-opus-5"})
        self.assertFalse(profile.governance_ready)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
