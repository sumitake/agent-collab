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
_TAG_RE = re.compile(r"\Av[0-9]+\.[0-9]+\.[0-9]+\Z")

# The ONLY path a release-only commit may touch. Everything else — and most
# pointedly the publishing workflow and the GPG trust anchor — is forbidden.
MANIFEST_PATH = "plugins/agent-collab/runtime-manifest.json"
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


def assert_release_commit_delta(changed_paths: list[str], *, parent_manifest: str,
                                release_manifest: str) -> None:
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

    try:
        before = json.loads(parent_manifest)
        after = json.loads(release_manifest)
    except ValueError as exc:
        raise TagContractError("release-commit manifest is not valid JSON") from exc
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise TagContractError("release-commit manifest must be a JSON object")

    if before.get("artifacts"):
        raise TagContractError(
            "parent (main) commit already carries activation artifacts — "
            "main must never carry them (per-release, not per-branch)"
        )
    artifacts = after.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise TagContractError(
            "release-only commit must add exactly one activation artifact"
        )

    before_rest = {k: v for k, v in before.items() if k != "artifacts"}
    after_rest = {k: v for k, v in after.items() if k != "artifacts"}
    if before_rest != after_rest:
        differing = sorted(
            k for k in set(before_rest) | set(after_rest)
            if before_rest.get(k) != after_rest.get(k)
        )
        raise TagContractError(
            "release-only commit changed manifest field(s) other than 'artifacts': "
            + ", ".join(differing)
        )
