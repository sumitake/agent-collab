"""Path-2 broker notarization tri-state (issue #36).

Behavioral coverage for the broker-verification lifecycle path:
  (a) G3 — notary-unconfirmed yields UNAVAILABLE; spawn/adopt does not proceed;
      mutation paths still roll back.
  (b) G2 — genuine signature/digest corruption stays hard.
  (c) Catch-ordering — per-terminal UNAVAILABLE (mis-ordered catch fails).
  (d) Class A — stage/commit/abort: restored_previous + UNAVAILABLE together.

Injection point is the notarization inspector path (``_RuntimeNotarizationUnavailable``
raised from the published-version verify chain), never string-matching messages.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, patch

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "agent-collab"
_RC_PATH = PLUGIN_DIR / "runtime_client.py"


def _load_runtime_client():
    name = "agent_collab_runtime_client_path2_notary_test"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, _RC_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rc = _load_runtime_client()


NOTARY_MSG = rc._NOTARIZATION_UNAVAILABLE_MESSAGE


def _raise_notary(*_a: Any, **_k: Any):
    raise rc._RuntimeNotarizationUnavailable(NOTARY_MSG)


def _raise_signature(*_a: Any, **_k: Any):
    raise rc._RuntimeSignatureError("macOS code signature verification failed")


def _raise_broker_notary(*_a: Any, **_k: Any):
    raise rc._BrokerNotarizationUnavailable(NOTARY_MSG)


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *args: Any):
        return False


class TestPath2BrokerNotarization(unittest.TestCase):
    def _enter(self, cm):
        """Python 3.10-safe context-manager entry (TestCase.enterContext is 3.11+)."""
        value = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return value
    """Path-2 broker notarization tri-state behavioral tests."""

    def _notary_at_verify(self):
        """Inject notary-unconfirmed at the source verify path (inspector → re-type)."""

        def wrapped(*args: Any, **kwargs: Any):
            raise rc._BrokerNotarizationUnavailable(NOTARY_MSG)

        self._enter(patch.object(rc, "_verify_published_version", wrapped))
        return wrapped

    def _signature_at_verify(self):
        """Inject genuine signature corruption (must stay HARD)."""

        def wrapped(*_a: Any, **_k: Any):
            raise ValueError("provider broker bundle identity mismatch")

        self._enter(patch.object(rc, "_verify_published_version", wrapped))
        return wrapped

    # ---------------------------------------------------------------------------
    # (b) G2 — genuine corruption stays hard
    # ---------------------------------------------------------------------------

    def test_source_retype_preserves_signature_as_valueerror(self):
        """_RuntimeSignatureError still flattens to hard ValueError at source.

        Replays the exact two-except ordering from ``_verify_published_version``:
        specific ``_RuntimeNotarizationUnavailable`` first, then generic
        ``BundleContractError``. A signature error (``_RuntimeSignatureError``, a
        ``BundleContractError`` subclass that is NOT ``_RuntimeNotarizationUnavailable``)
        must NOT match the notary re-type branch and must fall through to the second
        handler, which raises the plain hard ``ValueError``.
        """
        signature_exc = rc._RuntimeSignatureError(
            "macOS code signature verification failed"
        )
        self.assertIsInstance(signature_exc, rc.runtime_bundle.BundleContractError)
        self.assertNotIsInstance(signature_exc, rc._RuntimeNotarizationUnavailable)

        # Replay the catch ordering: signature must skip notary branch, hit BundleContractError.
        reached_second_branch = False
        try:
            try:
                raise signature_exc
            except rc._RuntimeNotarizationUnavailable:
                self.fail(
                    "signature error must not match notary type "
                    "(first except must not catch _RuntimeSignatureError)"
                )
            except rc.runtime_bundle.BundleContractError as exc:
                reached_second_branch = True
                # Second branch: non-notary BundleContractError → hard ValueError
                with self.assertRaisesRegex(
                    ValueError, "provider broker bundle identity mismatch"
                ):
                    raise ValueError(
                        "provider broker bundle identity mismatch"
                    ) from exc
        except AssertionError:
            raise
        except Exception as unexpected:
            self.fail(f"unexpected exception from catch-order replay: {unexpected!r}")

        self.assertTrue(
            reached_second_branch,
            "signature error must reach the second (BundleContractError) branch",
        )

        # Contrast: notary error must hit the FIRST branch only.
        notary_reached_first = False
        notary_reached_second = False
        try:
            try:
                raise rc._RuntimeNotarizationUnavailable(NOTARY_MSG)
            except rc._RuntimeNotarizationUnavailable as exc:
                notary_reached_first = True
                raise rc._BrokerNotarizationUnavailable(str(exc)) from exc
            except rc.runtime_bundle.BundleContractError:
                notary_reached_second = True
        except rc._BrokerNotarizationUnavailable:
            pass

        self.assertTrue(
            notary_reached_first,
            "notary error must match the first (_RuntimeNotarizationUnavailable) branch",
        )
        self.assertFalse(
            notary_reached_second,
            "notary error must not fall through to the generic BundleContractError branch",
        )

    def test_source_retype_notary_becomes_broker_notary(self):
        """_RuntimeNotarizationUnavailable is re-typed to _BrokerNotarizationUnavailable."""
        try:
            try:
                raise rc._RuntimeNotarizationUnavailable(NOTARY_MSG)
            except rc._RuntimeNotarizationUnavailable as exc:
                raise rc._BrokerNotarizationUnavailable(str(exc)) from exc
        except rc._BrokerNotarizationUnavailable as broker_exc:
            self.assertIn(NOTARY_MSG, str(broker_exc))
            self.assertIsInstance(broker_exc, ValueError)
            self.assertNotIsInstance(broker_exc, rc._RuntimeSignatureError)

    def test_verify_published_version_source_retype_real(self):
        """REAL _verify_published_version: a notary miss at verify_bundle_tree is
        re-typed to _BrokerNotarizationUnavailable (exercises the actual EDIT-4 source
        re-type, not a hand-replay). Closes the Codex R2 low/non-blocking concern."""
        import hashlib

        artifact = "a" * 64
        manifest_raw = b'{"schema": 1}'
        manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
        entry = {"sha256": artifact, "_files": [], "signing": {}, "_anchor": None}

        # Get past every pre-verify gate so the REAL function reaches verify_bundle_tree.
        self._enter(
            patch.object(rc, "_broker_version_path", lambda *a, **k: Path("/tmp/v"))
        )
        self._enter(patch.object(rc, "_exact_mode", lambda *a, **k: MagicMock()))
        self._enter(
            patch.object(
                rc, "_read_regular_nofollow", lambda *a, **k: (manifest_raw, MagicMock())
            )
        )
        self._enter(
            patch.object(
                rc.runtime_bundle, "load_closed_json_object", lambda _r: {"doc": True}
            )
        )
        self._enter(patch.object(rc, "_manifest_entry", lambda *a, **k: (entry, None)))
        self._enter(
            patch.object(
                Path,
                "iterdir",
                lambda self: [
                    Path("agent-collab-runtime.bundle"),
                    Path(rc.MANIFEST_NAME),
                ],
            )
        )
        # The inspector (verify_bundle_tree) raises the CONSUMER notary type; the real
        # source re-type must convert it to the BROKER type.
        self._enter(
            patch.object(rc.runtime_bundle, "verify_bundle_tree", _raise_notary)
        )
        with self.assertRaises(rc._BrokerNotarizationUnavailable):
            rc._verify_published_version(
                Path("/tmp/x"),
                artifact_digest=artifact,
                manifest_digest=manifest_digest,
            )

    def test_verify_published_version_signature_stays_hard_real(self):
        """REAL _verify_published_version: a genuine signature error is NOT re-typed —
        it falls through to the generic BundleContractError→ValueError hard path (G2)."""
        import hashlib

        artifact = "a" * 64
        manifest_raw = b'{"schema": 1}'
        manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
        entry = {"sha256": artifact, "_files": [], "signing": {}, "_anchor": None}
        self._enter(
            patch.object(rc, "_broker_version_path", lambda *a, **k: Path("/tmp/v"))
        )
        self._enter(patch.object(rc, "_exact_mode", lambda *a, **k: MagicMock()))
        self._enter(
            patch.object(
                rc, "_read_regular_nofollow", lambda *a, **k: (manifest_raw, MagicMock())
            )
        )
        self._enter(
            patch.object(
                rc.runtime_bundle, "load_closed_json_object", lambda _r: {"doc": True}
            )
        )
        self._enter(patch.object(rc, "_manifest_entry", lambda *a, **k: (entry, None)))
        self._enter(
            patch.object(
                Path,
                "iterdir",
                lambda self: [
                    Path("agent-collab-runtime.bundle"),
                    Path(rc.MANIFEST_NAME),
                ],
            )
        )
        self._enter(
            patch.object(rc.runtime_bundle, "verify_bundle_tree", _raise_signature)
        )
        with self.assertRaises(ValueError) as ctx:
            rc._verify_published_version(
                Path("/tmp/x"),
                artifact_digest=artifact,
                manifest_digest=manifest_digest,
            )
        self.assertNotIsInstance(ctx.exception, rc._BrokerNotarizationUnavailable)

    # ---------------------------------------------------------------------------
    # (c) Catch-ordering / Class-B terminals → UNAVAILABLE
    # ---------------------------------------------------------------------------

    def test_load_broker_state_notary_returns_unavailable(self):
        """Exercises the REAL _load_broker_state; notary injected at _verify_published_version."""
        artifact, manifest = "a" * 64, "b" * 64
        raw = (
            b'{"artifact_sha256": "' + artifact.encode()
            + b'", "manifest_sha256": "' + manifest.encode() + b'"}'
        )
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        # Get past the pre-verify gates (existence, perms, read, schema) so the REAL
        # function reaches its real _verify_published_version call and its real terminal.
        self._enter(patch.object(Path, "lstat", lambda self: MagicMock()))
        self._enter(
            patch.object(rc, "_exact_mode", lambda *_a, **_k: MagicMock(st_size=len(raw)))
        )
        self._enter(
            patch.object(
                rc, "_read_regular_nofollow", lambda *_a, **_k: (raw, MagicMock())
            )
        )
        self._enter(patch.object(rc, "_broker_record_valid", lambda *_a, **_k: True))
        self._enter(patch.object(rc, "_verify_published_version", _raise_broker_notary))

        state, err = rc._load_broker_state(
            artifact_digest=artifact, manifest_digest=manifest, require_socket=False
        )
        self.assertIsNone(state)
        self.assertIsNotNone(err)
        self.assertIs(err.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(err.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    def test_capture_broker_lanes_notary_returns_unavailable_tuple(self):
        resolution = rc.RuntimeResolution(
            status=rc.RuntimeStatus.OK,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
        )
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        self._enter(
            patch.object(
                rc,
                "_read_broker_selector_view",
                _raise_broker_notary,
            )
        )
        lanes, err = rc._capture_broker_lanes(resolution)
        self.assertEqual(lanes, ())
        self.assertIsNotNone(err)
        self.assertIs(err.status, rc.RuntimeStatus.UNAVAILABLE)

    def test_dispatcher_status_notary_returns_unavailable(self):
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        self._enter(
            patch.object(
                Path,
                "lstat",
                lambda self: MagicMock(st_mode=0o040700, st_uid=0, st_nlink=1),
                create=True,
            )
        )
        # Force the view read to raise the broker notary marker.
        self._enter(
            patch.object(rc, "_read_broker_selector_view", _raise_broker_notary)
        )
        # Root mode check may fail first; patch _exact_mode to pass.
        self._enter(
            patch.object(
                rc,
                "_exact_mode",
                lambda *_a, **_k: MagicMock(st_mode=0o040700, st_uid=0, st_nlink=2),
            )
        )
        result = rc.dispatcher_status()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    def test_invoke_dispatcher_ping_notary_returns_unavailable(self):
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        self._enter(
            patch.object(rc, "_read_broker_selector_view", _raise_broker_notary)
        )
        result = rc.invoke_dispatcher_ping()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    def test_recover_notary_returns_unavailable(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        self._enter(
            patch.object(
                rc,
                "_broker_control_lock",
                lambda _root: _nullcontext(),
            )
        )
        self._enter(
            patch.object(rc, "_read_broker_selector_view", _raise_broker_notary)
        )
        result = rc.recover_last_committed_control_plane()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(result.result, {"recovered": False})
        self.assertIsNot(result.status, rc.RuntimeStatus.PROVIDER_ERROR)

    def test_drain_notary_returns_unavailable(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        self._enter(
            patch.object(
                rc,
                "_broker_control_lock",
                lambda _root: _nullcontext(),
            )
        )
        self._enter(
            patch.object(rc, "_read_selector_v2_snapshot", _raise_broker_notary)
        )
        result = rc.drain_retiring_dispatcher()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(result.result, {"retained_drained": False})

    def test_install_broker_notary_returns_unavailable(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(
            patch.object(
                rc,
                "resolve_runtime",
                lambda: rc.RuntimeResolution(
                    status=rc.RuntimeStatus.OK,
                    path=Path("/tmp/runtime"),
                    bundle_path=Path("/tmp/bundle"),
                    artifact_digest="a" * 64,
                    manifest_digest="b" * 64,
                    identity=MagicMock(),
                    files=({"path": "x"},),
                    contracts=frozenset({("grok", "architecture")}),
                    anchor=rc.RuntimeContractAnchor("3.0.0", 3),
                ),
            )
        )
        self._enter(patch.object(rc, "_ensure_broker_layout", _raise_broker_notary))
        result = rc.install_broker()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    def test_rollback_broker_notary_returns_unavailable(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        # root.exists True
        self._enter(patch.object(Path, "exists", lambda self: True, create=True))
        self._enter(
            patch.object(
                rc,
                "_broker_control_lock",
                lambda _root: _nullcontext(),
            )
        )
        self._enter(
            patch.object(rc, "_read_selector_v2_snapshot", lambda _r: (None, None))
        )
        self._enter(
            patch.object(rc, "_read_current_broker_state", _raise_broker_notary)
        )
        result = rc.rollback_broker()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    def test_uninstall_broker_notary_returns_unavailable(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(patch.object(rc, "_broker_root", lambda: Path("/tmp/x")))
        self._enter(patch.object(Path, "exists", lambda self: True, create=True))
        self._enter(
            patch.object(
                rc,
                "_broker_control_lock",
                lambda _root: _nullcontext(),
            )
        )
        self._enter(
            patch.object(rc, "_read_broker_selector_v2", _raise_broker_notary)
        )
        result = rc.uninstall_broker()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    def test_activate_broker_record_initial_notary_unavailable(self):
        self._enter(
            patch.object(rc, "_verify_published_version", _raise_broker_notary)
        )
        result = rc._activate_broker_record(
            Path("/tmp/x"),
            target_artifact="a" * 64,
            target_manifest="b" * 64,
            current_state=None,
            next_previous=None,
            restore_state=None,
        )
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        # G3: must not report OK / must not look like a successful install.
        self.assertTrue(
            result.result is None or result.result.get("installed") is not True
        )

    def test_activate_broker_record_r2_preserves_unavailable_from_load(self):
        """R2: readback UNAVAILABLE must not become PROVIDER_ERROR via RuntimeError."""
        runtime_path = Path("/tmp/runtime-entry")

        def fake_verify(*_a: Any, **_k: Any):
            return Path("/tmp/b"), runtime_path, Path("/tmp/m"), None

        self._enter(patch.object(rc, "_verify_published_version", fake_verify))
        self._enter(patch.object(rc, "_operator_home", lambda: "/tmp/home"))
        self._enter(
            patch.object(
                rc,
                "_broker_plist_document",
                lambda **_k: {"Label": rc.BROKER_LABEL},
            )
        )
        self._enter(patch.object(rc, "_plist_bytes", lambda _d: b"<plist/>"))
        self._enter(
            patch.object(
                rc,
                "_record_for",
                lambda **_k: {
                    "schema_version": 2,
                    "artifact_sha256": "a" * 64,
                    "manifest_sha256": "b" * 64,
                },
            )
        )
        bootout = self._enter(
            patch.object(rc, "_bootout_broker", MagicMock(return_value=True))
        )
        self._enter(
            patch.object(rc, "_write_private_atomic", lambda *_a, **_k: None)
        )
        self._enter(patch.object(rc, "_bootstrap_broker", lambda _p: True))
        self._enter(patch.object(rc, "_broker_job_loaded", lambda: True))
        self._enter(
            patch.object(rc, "_exact_mode", lambda *_a, **_k: MagicMock())
        )
        self._enter(patch.object(rc, "_broker_ping", lambda _p: True))

        unavailable = rc.RuntimeResult(
            rc.RuntimeStatus.UNAVAILABLE, error=NOTARY_MSG
        )
        self._enter(
            patch.object(
                rc,
                "_load_broker_state",
                lambda **_k: (None, unavailable),
            )
        )

        result = rc._activate_broker_record(
            Path("/tmp/x"),
            target_artifact="a" * 64,
            target_manifest="b" * 64,
            current_state=None,
            next_previous=None,
            restore_state=None,
        )
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.PROVIDER_ERROR)
        # Concern-1 regression guard (from the Codex peer review): a post-bootstrap
        # readback notary miss MUST roll back (bootout the just-activated candidate)
        # BEFORE reporting UNAVAILABLE — never an early return that leaves it running.
        # current_state=None ⇒ the mutation try does no bootout, so a called bootout
        # can ONLY be the rollback one. (This assertion FAILS against the old early-return.)
        self.assertTrue(
            bootout.called,
            "rollback bootout must run on a post-bootstrap notary miss",
        )
        self.assertIsNotNone(result.result)
        self.assertIn("restored_previous", result.result)

    # ---------------------------------------------------------------------------
    # (a) G3 — no spawn/adopt of unverified; mutation rollback still runs
    # ---------------------------------------------------------------------------

    def test_g3_stage_notary_unavailable_and_rollback_runs(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(
            patch.object(
                rc,
                "resolve_runtime",
                lambda: rc.RuntimeResolution(
                    status=rc.RuntimeStatus.OK,
                    path=Path("/tmp/runtime"),
                    bundle_path=Path("/tmp/bundle"),
                    artifact_digest="a" * 64,
                    manifest_digest="b" * 64,
                    identity=MagicMock(),
                    files=({"path": "x"},),
                    contracts=frozenset({("grok", "architecture")}),
                    anchor=rc.RuntimeContractAnchor("3.0.0", 3),
                ),
            )
        )
        root = Path("/tmp/broker-root-path2")
        self._enter(patch.object(rc, "_ensure_broker_layout", lambda: root))

        rollback_calls: list[bool] = []

        def fake_transaction(_root: Path, *, rollback: Callable[[], bool]):
            class _Tx:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    if exc is not None:
                        try:
                            restored = rollback()
                        except Exception:
                            restored = False
                        rollback_calls.append(True)
                        retryable = isinstance(exc, rc._BrokerNotarizationUnavailable)
                        raise rc._BrokerMutationFailure(
                            restored_previous=restored, retryable=retryable
                        ) from exc
                    return False

            return _Tx()

        self._enter(
            patch.object(rc, "_broker_control_transaction", fake_transaction)
        )
        self._enter(
            patch.object(rc, "_read_selector_v2_snapshot", lambda _r: (None, None))
        )
        # Baseline present so stage proceeds to verify.
        baseline = {
            "schema_version": 2,
            "generation": 1,
            "selector_v1_sha256": None,
            "selected": {
                "artifact_sha256": "c" * 64,
                "manifest_sha256": "d" * 64,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": 1,
            },
            "retained": None,
            "candidate": None,
            "lifecycle": None,
        }
        self._enter(
            patch.object(rc, "_read_broker_selector_view", lambda _r: baseline)
        )
        self._enter(
            patch.object(rc, "_publish_broker_version", lambda *_a, **_k: None)
        )
        self._enter(
            patch.object(
                rc,
                "_dispatcher_lane_snapshot",
                lambda *_a, **_k: rc.BrokerLaneSnapshot(
                    name="candidate",
                    generation=2,
                    artifact_digest="a" * 64,
                    manifest_digest="b" * 64,
                    label="com.agent-collab.provider-dispatcher." + "0" * 32,
                    socket_path=root / "sock",
                    transport="dispatcher",
                    protocol_version=2,
                    anchor=rc.RuntimeContractAnchor("3.0.0", 3),
                ),
            )
        )
        # No untracked paths.
        self._enter(patch.object(Path, "exists", lambda self: False, create=True))
        self._enter(
            patch.object(Path, "is_symlink", lambda self: False, create=True)
        )
        self._enter(
            patch.object(rc, "_verify_published_version", _raise_broker_notary)
        )

        result = rc.stage_dispatcher()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.PROVIDER_ERROR)
        self.assertIsNotNone(result.result)
        self.assertIn("restored_previous", result.result)
        self.assertTrue(rollback_calls, "G4: transaction rollback must run on notary miss")
        # G3: staging did not succeed
        self.assertIsNot(result.result.get("staged"), True)

    def test_g3_commit_notary_unavailable_and_rollback_runs(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        root = Path("/tmp/broker-root-path2")
        self._enter(patch.object(rc, "_broker_root", lambda: root))

        rollback_calls: list[bool] = []

        def fake_transaction(_root: Path, *, rollback: Callable[[], bool]):
            class _Tx:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    if exc is not None:
                        try:
                            restored = rollback()
                        except Exception:
                            restored = False
                        rollback_calls.append(restored)
                        retryable = isinstance(exc, rc._BrokerNotarizationUnavailable)
                        raise rc._BrokerMutationFailure(
                            restored_previous=True, retryable=retryable
                        ) from exc
                    return False

            return _Tx()

        self._enter(
            patch.object(rc, "_broker_control_transaction", fake_transaction)
        )
        selector = {
            "schema_version": 2,
            "generation": 1,
            "selector_v1_sha256": None,
            "selected": {
                "artifact_sha256": "c" * 64,
                "manifest_sha256": "d" * 64,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": 1,
            },
            "retained": None,
            "candidate": {
                "artifact_sha256": "a" * 64,
                "manifest_sha256": "b" * 64,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": 2,
            },
            "lifecycle": None,
        }
        self._enter(
            patch.object(rc, "_read_selector_v2_snapshot", lambda _r: (selector, b"{}"))
        )
        self._enter(
            patch.object(rc, "_load_selector_v2_lane", _raise_broker_notary)
        )

        result = rc.commit_dispatcher_selector()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNotNone(result.result)
        self.assertIs(result.result.get("restored_previous"), True)
        self.assertTrue(rollback_calls, "G4: rollback must run")
        self.assertIsNot(result.result.get("committed"), True)

    def test_g3_abort_notary_unavailable_and_rollback_runs(self):
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        root = Path("/tmp/broker-root-path2")
        self._enter(patch.object(rc, "_broker_root", lambda: root))

        rollback_calls: list[bool] = []

        def fake_transaction(_root: Path, *, rollback: Callable[[], bool]):
            class _Tx:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    if exc is not None:
                        try:
                            restored = rollback()
                        except Exception:
                            restored = False
                        rollback_calls.append(restored)
                        retryable = isinstance(exc, rc._BrokerNotarizationUnavailable)
                        raise rc._BrokerMutationFailure(
                            restored_previous=True, retryable=retryable
                        ) from exc
                    return False

            return _Tx()

        self._enter(
            patch.object(rc, "_broker_control_transaction", fake_transaction)
        )
        selector = {
            "schema_version": 2,
            "generation": 1,
            "selector_v1_sha256": None,
            "selected": {
                "artifact_sha256": "c" * 64,
                "manifest_sha256": "d" * 64,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": 1,
            },
            "retained": None,
            "candidate": {
                "artifact_sha256": "a" * 64,
                "manifest_sha256": "b" * 64,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": 2,
            },
            "lifecycle": None,
        }
        self._enter(
            patch.object(rc, "_read_selector_v2_snapshot", lambda _r: (selector, b"{}"))
        )
        self._enter(
            patch.object(rc, "_load_selector_v2_lane", _raise_broker_notary)
        )

        result = rc.abort_dispatcher_candidate()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNotNone(result.result)
        self.assertIs(result.result.get("restored_previous"), True)
        self.assertTrue(rollback_calls, "G4: rollback must run")
        self.assertIsNot(result.result.get("aborted"), True)

    def test_g2_stage_genuine_corruption_stays_provider_error(self):
        """Hard integrity failure on mutation path must not become UNAVAILABLE."""
        self._enter(
            patch.object(rc, "_broker_lifecycle_seatbelt_block", lambda: None)
        )
        self._enter(
            patch.object(
                rc,
                "resolve_runtime",
                lambda: rc.RuntimeResolution(
                    status=rc.RuntimeStatus.OK,
                    path=Path("/tmp/runtime"),
                    bundle_path=Path("/tmp/bundle"),
                    artifact_digest="a" * 64,
                    manifest_digest="b" * 64,
                    identity=MagicMock(),
                    files=({"path": "x"},),
                    contracts=frozenset({("grok", "architecture")}),
                    anchor=rc.RuntimeContractAnchor("3.0.0", 3),
                ),
            )
        )
        root = Path("/tmp/broker-root-path2")
        self._enter(patch.object(rc, "_ensure_broker_layout", lambda: root))

        def fake_transaction(_root: Path, *, rollback: Callable[[], bool]):
            class _Tx:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    if exc is not None:
                        try:
                            restored = rollback()
                        except Exception:
                            restored = False
                        retryable = isinstance(exc, rc._BrokerNotarizationUnavailable)
                        raise rc._BrokerMutationFailure(
                            restored_previous=restored, retryable=retryable
                        ) from exc
                    return False

            return _Tx()

        self._enter(
            patch.object(rc, "_broker_control_transaction", fake_transaction)
        )
        self._enter(
            patch.object(rc, "_read_selector_v2_snapshot", lambda _r: (None, None))
        )
        baseline = {
            "schema_version": 2,
            "generation": 1,
            "selector_v1_sha256": None,
            "selected": {
                "artifact_sha256": "c" * 64,
                "manifest_sha256": "d" * 64,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": 1,
            },
            "retained": None,
            "candidate": None,
            "lifecycle": None,
        }
        self._enter(
            patch.object(rc, "_read_broker_selector_view", lambda _r: baseline)
        )
        self._enter(
            patch.object(rc, "_publish_broker_version", lambda *_a, **_k: None)
        )
        self._enter(
            patch.object(
                rc,
                "_dispatcher_lane_snapshot",
                lambda *_a, **_k: rc.BrokerLaneSnapshot(
                    name="candidate",
                    generation=2,
                    artifact_digest="a" * 64,
                    manifest_digest="b" * 64,
                    label="com.agent-collab.provider-dispatcher." + "0" * 32,
                    socket_path=root / "sock",
                    transport="dispatcher",
                    protocol_version=2,
                    anchor=rc.RuntimeContractAnchor("3.0.0", 3),
                ),
            )
        )
        self._enter(patch.object(Path, "exists", lambda self: False, create=True))
        self._enter(
            patch.object(Path, "is_symlink", lambda self: False, create=True)
        )

        def hard_verify(*_a: Any, **_k: Any):
            raise ValueError("provider broker bundle identity mismatch")

        self._enter(patch.object(rc, "_verify_published_version", hard_verify))

        result = rc.stage_dispatcher()
        self.assertIs(result.status, rc.RuntimeStatus.PROVIDER_ERROR)
        self.assertIsNot(result.status, rc.RuntimeStatus.UNAVAILABLE)

    # ---------------------------------------------------------------------------
    # Swallow (a) — broker_status must not silent-deny rollback on notary miss
    # ---------------------------------------------------------------------------

    def test_broker_status_rollback_readiness_notary_surfaces_unavailable(self):
        root = Path("/tmp/broker-status-path2")
        self._enter(patch.object(rc, "_broker_root", lambda: root))
        self._enter(patch.object(Path, "exists", lambda self: True, create=True))
        self._enter(
            patch.object(
                rc,
                "_exact_mode",
                lambda *_a, **_k: MagicMock(st_mode=0o040700, st_uid=0, st_nlink=2),
            )
        )
        # Force legacy state path (no selector-v2 view).
        self._enter(
            patch.object(rc, "_read_broker_selector_view", lambda _r: None)
        )
        state = {
            "schema_version": 2,
            "contract_version": 3,
            "broker_protocol_version": 2,
            "runtime_protocol_version": 2,
            "artifact_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "plist_sha256": "c" * 64,
            "label": rc.BROKER_LABEL,
            "bundle_path": str(root / "versions" / "x" / "agent-collab-runtime.bundle"),
            "entrypoint_path": str(
                root / "versions" / "x" / "agent-collab-runtime.bundle" / "entry"
            ),
            "manifest_path": str(root / "versions" / "x" / "runtime-manifest.json"),
            "socket_path": str(root / "provider-broker.sock"),
            "previous": {
                "schema_version": 2,
                "contract_version": 3,
                "broker_protocol_version": 2,
                "runtime_protocol_version": 2,
                "artifact_sha256": "d" * 64,
                "manifest_sha256": "e" * 64,
                "plist_sha256": "f" * 64,
                "label": rc.BROKER_LABEL,
                "bundle_path": str(root / "versions" / "y" / "agent-collab-runtime.bundle"),
                "entrypoint_path": str(
                    root / "versions" / "y" / "agent-collab-runtime.bundle" / "entry"
                ),
                "manifest_path": str(root / "versions" / "y" / "runtime-manifest.json"),
                "socket_path": str(root / "provider-broker.sock"),
                "previous": None,
            },
        }
        self._enter(
            patch.object(rc, "_read_current_broker_state", lambda _r: dict(state))
        )
        self._enter(
            patch.object(rc, "_verify_plist_against_state", lambda *_a, **_k: None)
        )
        self._enter(patch.object(rc, "_broker_job_loaded", lambda: False))

        calls = {"n": 0}

        def verify_side_effect(*_a: Any, **_k: Any):
            calls["n"] += 1
            if calls["n"] == 1:
                # current version ok
                return Path("/t"), Path("/t/e"), Path("/t/m"), None
            # previous (rollback readiness) → notary miss
            raise rc._BrokerNotarizationUnavailable(NOTARY_MSG)

        self._enter(
            patch.object(rc, "_verify_published_version", verify_side_effect)
        )

        result = rc.broker_status()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        err_lower = (result.error or "").lower()
        self.assertTrue(
            "rollback readiness" in err_lower
            or "notary" in err_lower
            or "notarization" in err_lower
        )
        # Must NOT silently report rollback_available=False under a success-shaped body
        # without surfacing the notary condition.
        if result.result is not None:
            self.assertTrue(
                result.result.get("rollback_available") is not False or result.error
            )

    def test_broker_status_outer_notary_unavailable(self):
        root = Path("/tmp/broker-status-path2")
        self._enter(patch.object(rc, "_broker_root", lambda: root))
        self._enter(patch.object(Path, "exists", lambda self: True, create=True))
        self._enter(
            patch.object(
                rc,
                "_exact_mode",
                lambda *_a, **_k: MagicMock(st_mode=0o040700, st_uid=0, st_nlink=2),
            )
        )
        self._enter(
            patch.object(rc, "_read_broker_selector_view", _raise_broker_notary)
        )
        result = rc.broker_status()
        self.assertIs(result.status, rc.RuntimeStatus.UNAVAILABLE)
        self.assertIsNot(result.status, rc.RuntimeStatus.INTEGRITY_ERROR)

    # ---------------------------------------------------------------------------
    # MutationFailure.retryable field contract
    # ---------------------------------------------------------------------------

    def test_broker_mutation_failure_retryable_default_false(self):
        failure = rc._BrokerMutationFailure(restored_previous=True)
        self.assertIs(failure.restored_previous, True)
        self.assertIs(failure.retryable, False)

    def test_broker_mutation_failure_retryable_explicit(self):
        failure = rc._BrokerMutationFailure(restored_previous=False, retryable=True)
        self.assertIs(failure.retryable, True)
        self.assertIs(failure.restored_previous, False)

    def test_broker_control_transaction_sets_retryable_on_notary(self):
        self._enter(
            patch.object(
                rc,
                "_broker_control_lock",
                lambda _root: _nullcontext(),
            )
        )
        rolled = {"n": 0}

        def rollback() -> bool:
            rolled["n"] += 1
            return True

        with self.assertRaises(rc._BrokerMutationFailure) as caught:
            with rc._broker_control_transaction(Path("/tmp/x"), rollback=rollback):
                raise rc._BrokerNotarizationUnavailable(NOTARY_MSG)
        self.assertIs(caught.exception.retryable, True)
        self.assertIs(caught.exception.restored_previous, True)
        self.assertEqual(rolled["n"], 1)

    def test_broker_control_transaction_hard_error_not_retryable(self):
        self._enter(
            patch.object(
                rc,
                "_broker_control_lock",
                lambda _root: _nullcontext(),
            )
        )
        rolled = {"n": 0}

        def rollback() -> bool:
            rolled["n"] += 1
            return True

        with self.assertRaises(rc._BrokerMutationFailure) as caught:
            with rc._broker_control_transaction(Path("/tmp/x"), rollback=rollback):
                raise ValueError("provider broker bundle identity mismatch")
        self.assertIs(caught.exception.retryable, False)
        self.assertEqual(rolled["n"], 1)


if __name__ == "__main__":
    unittest.main()