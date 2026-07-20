#!/usr/bin/env python3
"""Signed-tag grammar and release-commit topology gates.

Design of record: `docs/design/pr4-cut-release-activation-design.md` V3/V9
(converged through a 2-round distinct-family adversarial design review).

The signed annotated tag is the release's trust anchor: CI verifies its
signature against an out-of-tree pinned key and takes the asset/manifest
digests FROM THE TAG (never from a dispatch payload or a local journal). That
makes the tag message a parsing surface an attacker will probe, so the grammar
is deliberately strict and total: exact field set, no duplicates, no unknown
fields, no extra material, canonical digest form. Anything else fails closed.

The release-only commit is the other half: its diff must be EXACTLY the
activation-artifacts insertion, so a release cut can never smuggle a change to
the workflow that publishes it or the trust anchor that authenticates it.
"""
from __future__ import annotations

import json
import re

SCHEMA = "agent-collab-release/1"
_REQUIRED = ("schema", "Asset-Name", "Asset-SHA256", "Manifest-SHA256")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")          # lowercase-only, canonical
_ASSET_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._ -]{0,127}\Z")
_TAG_RE = re.compile(r"\Av(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
# \A/\Z, never ^/$: `$` also matches BEFORE a trailing newline, so "v1.0.0\n"
# would pass and become a filename containing a newline. Leading zeros are
# rejected too — "v01.0.0" and "v1.0.0" must not be two names for one release.

# The ONLY path a release-only commit may touch. Everything else — and most
# pointedly the publishing workflow and the GPG trust anchor — is forbidden.
MANIFEST_PATH = "plugins/agent-collab/runtime-manifest.json"
# An artifact entry must actually describe the shipped archive, not merely exist.
REQUIRED_ARTIFACT_FIELDS = ("platform", "sha256", "size_bytes", "runtime_identity")
# A regular non-executable file. The release commit must not change it.
EXPECTED_MANIFEST_MODE = "100644"
FORBIDDEN_PREFIXES = (".github/", ".gpgkeys/", "scripts/", "plugins/agent-collab/runtime/")


class TagContractError(ValueError):
    """The tag message or release commit violates the release contract."""


def validate_tag_name(tag: str) -> str:
    """Reject any tag string before it is used in a path, ref, or command.

    `revocations/<tag>.json` and `refs/tags/<tag>` both interpolate this, so a
    traversal or ref-injection attempt must be stopped at the boundary rather
    than deep inside a filesystem or git operation.
    """
    if not isinstance(tag, str) or not _TAG_RE.match(tag):
        raise TagContractError(f"tag must be vMAJOR.MINOR.PATCH, got {tag!r}")
    return tag


def format_tag_message(tag: str, *, asset_name: str, asset_sha256: str,
                       manifest_sha256: str) -> str:
    """Render the canonical signed-tag message (the only accepted form)."""
    validate_tag_name(tag)
    message = (
        f"agent-collab {tag}\n"
        f"schema: {SCHEMA}\n"
        f"Asset-Name: {asset_name}\n"
        f"Asset-SHA256: {asset_sha256}\n"
        f"Manifest-SHA256: {manifest_sha256}\n"
    )
    parse_tag_message(message, tag=tag)   # never emit what we would not accept
    return message


def parse_tag_message(message: str, *, tag: str) -> dict[str, str]:
    """Strictly parse a signed-tag message. Fails closed on anything unexpected.

    Rejects: a wrong/missing title, unknown or duplicate fields, missing
    required fields, uppercase or malformed digests, unsafe asset names,
    non-ASCII, and any trailing material after the field block.
    """
    if not isinstance(message, str) or not message.strip():
        raise TagContractError("tag message is empty")
    if not message.isascii():
        raise TagContractError("tag message must be ASCII")

    validate_tag_name(tag)
    # Exactly one trailing newline and no other surrounding whitespace: accepting
    # "equal after strip()" would make several distinct byte sequences validate
    # as the same message, which is precisely what a canonical form forbids.
    if message != message.rstrip("\n") + "\n":
        raise TagContractError("tag message must end with exactly one newline")
    lines = message.rstrip("\n").split("\n")
    if not lines or not lines[0]:
        raise TagContractError("tag message is empty")
    if lines[0] != f"agent-collab {tag}":
        raise TagContractError(
            f"tag message title must be 'agent-collab {tag}', got {lines[0]!r}"
        )

    fields: dict[str, str] = {}
    order: list[str] = []
    for line in lines[1:]:
        if not line:
            raise TagContractError("tag message must not contain blank or trailing lines")
        if ": " not in line:
            raise TagContractError(f"unparsable tag message line: {line!r}")
        key, _, value = line.partition(": ")
        if key != key.strip() or value != value.strip():
            raise TagContractError(f"tag message line has stray whitespace: {line!r}")
        if key in fields:
            raise TagContractError(f"duplicate tag message field: {key}")
        if key not in _REQUIRED:
            raise TagContractError(f"unknown tag message field: {key}")
        fields[key] = value
        order.append(key)
    # Canonical form is ordered: one message, one byte sequence.
    if order != [k for k in _REQUIRED if k in fields]:
        raise TagContractError(f"tag message fields are out of canonical order: {order}")

    missing = [k for k in _REQUIRED if k not in fields]
    if missing:
        raise TagContractError(f"tag message is missing required field(s): {', '.join(missing)}")

    if fields["schema"] != SCHEMA:
        raise TagContractError(f"unsupported tag schema: {fields['schema']!r}")
    if not _ASSET_NAME_RE.match(fields["Asset-Name"]):
        raise TagContractError(f"unsafe asset name: {fields['Asset-Name']!r}")
    if "/" in fields["Asset-Name"] or "\\" in fields["Asset-Name"]:
        raise TagContractError("asset name must be a bare basename")
    for key in ("Asset-SHA256", "Manifest-SHA256"):
        if not _SHA256_RE.match(fields[key]):
            raise TagContractError(
                f"{key} must be 64 lowercase hex characters, got {fields[key]!r}"
            )
    return {
        "schema": fields["schema"],
        "asset_name": fields["Asset-Name"],
        "asset_sha256": fields["Asset-SHA256"],
        "manifest_sha256": fields["Manifest-SHA256"],
    }


def _type_strict_equal(left, right) -> bool:
    """Deep equality that also requires matching TYPES.

    Python's `==` is type-punning on JSON scalars: `3 == 3.0`, `1 == True`, and
    `0 == False` are all true. A plain `before_rest != after_rest` therefore
    approves a release-only commit that rewrites `schema_version: 3` to `3.0` or
    `1` to `true` — a real manifest change the gate reports as no change, which
    downstream consumers requiring actual integers then reject.

    This closes the CLASS. The same defect was fixed one level down for
    `size_bytes` last round; fixing only the leaf left every other field exposed,
    because the containing comparison was still `==`.
    """
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_type_strict_equal(left[k], right[k]) for k in left))
    if isinstance(left, list):
        return (len(left) == len(right)
                and all(_type_strict_equal(a, b) for a, b in zip(left, right)))
    return left == right


def _strict_json(text: str, which: str) -> dict:
    """Parse a manifest, refusing constructs that other JSON readers disagree on.

    `json.loads` silently keeps the LAST of duplicate keys and accepts `NaN` /
    `Infinity`, neither of which is standard JSON. Both are smuggling vectors
    here: this gate compares one reading of the bytes while the consumer that
    later trusts the tag's Manifest-SHA256 may read them differently, so a
    manifest can pass the check and mean something else downstream. Divergence
    between parsers is exactly what the strict grammar exists to eliminate.
    """
    def _no_duplicates(pairs):
        seen: dict = {}
        for key, value in pairs:
            if key in seen:
                raise TagContractError(
                    f"{which} manifest contains a duplicate key {key!r}; JSON readers "
                    "disagree on which wins, so this is refused rather than resolved"
                )
            seen[key] = value
        return seen

    try:
        parsed = json.loads(
            text, object_pairs_hook=_no_duplicates,
            parse_constant=lambda c: (_ for _ in ()).throw(
                TagContractError(f"{which} manifest contains the non-standard constant {c!r}")
            ),
        )
    except TagContractError:
        raise
    except ValueError as exc:
        raise TagContractError(f"{which} manifest is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise TagContractError(f"{which} manifest must be a JSON object")
    return parsed


def assert_release_commit_delta(changed_paths: list[str], *, parent_manifest: str,
                                release_manifest: str,
                                expected_artifact: dict,
                                parent_mode: str, release_mode: str) -> None:
    """Assert the release-only commit is EXACTLY the activation-artifacts insertion.

    A path-count check is not enough (design V3): the diff is validated
    SEMANTICALLY — the manifest must differ only by going from no artifacts to
    exactly one activation artifact, with every other manifest field byte-equal.
    """
    # Forbidden prefixes are checked FIRST and independently of the exact-match
    # gate. Ordering matters: if this ran after "paths == [MANIFEST_PATH]", the
    # only surviving path would be the manifest itself and this loop could never
    # fire — defence in depth that is actually dead code. Running it first means
    # a release commit touching the publishing workflow or the trust anchor is
    # reported as exactly that, by its own rule.
    for path in changed_paths:
        if path == MANIFEST_PATH:
            continue
        for prefix in FORBIDDEN_PREFIXES:
            if path.startswith(prefix):
                raise TagContractError(
                    f"release-only commit must never touch {prefix}* (found {path}) — "
                    "a release must not modify the workflow that publishes it or the "
                    "trust anchor that authenticates it"
                )
    if list(changed_paths) != [MANIFEST_PATH]:
        extra = [p for p in changed_paths if p != MANIFEST_PATH]
        raise TagContractError(
            "release-only commit must touch exactly "
            f"{MANIFEST_PATH}; it also touches: {extra or '(nothing — empty diff)'}"
        )

    # The manifest's FILE MODE is part of the topology this gate claims to pin.
    # Comparing only paths and JSON lets a commit flip 100644 -> 100755 while
    # inserting the artifact and still pass — an executable-bit change riding
    # along with a release, which is exactly the smuggling the semantic delta
    # exists to stop.
    if parent_mode != release_mode:
        raise TagContractError(
            f"release-only commit changed the manifest file mode "
            f"({parent_mode} -> {release_mode}); a release must not alter file modes"
        )
    if release_mode != EXPECTED_MANIFEST_MODE:
        raise TagContractError(
            f"manifest file mode must be {EXPECTED_MANIFEST_MODE}, got {release_mode}"
        )
    before = _strict_json(parent_manifest, "parent")
    after = _strict_json(release_manifest, "release")

    if "artifacts" in before and before["artifacts"] not in ([], None):
        raise TagContractError(
            "parent (main) commit already carries activation artifacts — "
            "main must never carry them (per-release, not per-branch)"
        )
    artifacts = after.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise TagContractError(
            "release-only commit must add exactly one activation artifact"
        )
    # Counting the artifact is not verifying it: `{"artifacts": [{}]}` and
    # `{"artifacts": ["attacker-controlled"]}` both have length 1. The entry must
    # actually describe the artifact the tag's Manifest-SHA256 will bind to.
    entry = artifacts[0]
    if not isinstance(entry, dict):
        raise TagContractError("the activation artifact must be a JSON object")
    # Key PRESENCE, not truthiness: `size_bytes: 0` is present-and-invalid, not
    # missing, and reporting it as missing sends the reader looking for the wrong
    # defect. Each field's own check below says what is actually wrong with it.
    missing = [k for k in REQUIRED_ARTIFACT_FIELDS if k not in entry]
    if missing:
        raise TagContractError(
            "activation artifact is missing required field(s): " + ", ".join(sorted(missing))
        )
    if not _SHA256_RE.match(str(entry.get("sha256", ""))):
        raise TagContractError(
            "activation artifact sha256 must be 64 lowercase hex characters"
        )
    # `type(...) is int`, not isinstance: bool subclasses int, so `size_bytes: true`
    # would otherwise satisfy an isinstance check and compare equal to 1.
    if type(entry.get("size_bytes")) is not int or entry["size_bytes"] <= 0:
        raise TagContractError("activation artifact size_bytes must be a positive integer")
    # REQUIRED, not optional. An optional pin is one the wiring can simply omit,
    # and a well-formed artifact describing the wrong archive would then sail
    # through — the gate would be satisfied by a caller that never used it.
    if not _type_strict_equal(entry, expected_artifact):
        raise TagContractError(
            "activation artifact does not match the artifact derived from the built "
            "archive; refusing to bind a tag digest to a manifest describing something else"
        )

    before_rest = {k: v for k, v in before.items() if k != "artifacts"}
    after_rest = {k: v for k, v in after.items() if k != "artifacts"}
    if not _type_strict_equal(before_rest, after_rest):
        differing = sorted(
            k for k in set(before_rest) | set(after_rest)
            if not _type_strict_equal(before_rest.get(k), after_rest.get(k))
        )
        raise TagContractError(
            "release-only commit changed manifest field(s) other than 'artifacts': "
            + ", ".join(differing)
        )
