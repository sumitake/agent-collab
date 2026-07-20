#!/usr/bin/env python3
"""Signed release-tag message grammar (fail-closed).

Design of record: `docs/design/release-cut-pipeline-v2-saga-design.md` (the v3
release-saga architecture) and `pr4-cut-release-activation-design.md` V3/V9.

In the v3 design the signed annotated tag WILL BE the release's trust anchor: CI is
to verify its signature against an out-of-tree pinned key and take the asset/manifest
digests FROM THE TAG (never from a dispatch payload or a local journal). Nothing
imports this module yet, so that flow is the intended future behaviour, not current
behaviour. It is what makes the tag message a parsing surface an attacker will probe,
so the grammar is deliberately strict and total: exact field set, canonical order, no duplicates, no unknown fields, no extra
material, canonical digest form, ASCII only, bare-basename asset names. Anything
else fails closed.

SCOPE: this module is the message GRAMMAR only. Two related gates are deliberately
NOT here and land with the v3 saga implementation:

* the release-commit topology gate — deferred because its artifact validation was
  built from design prose instead of the repository's own
  `runtime-manifest.schema.json`, and must be rebuilt against that schema;
* intent binding (repository id, release commit, channel, signer policy) — the v3
  design extends this grammar to carry the full signed intent, which closes
  cross-repository signature replay. The v1 grammar below binds only version,
  asset name and digests, so it must not yet be relied on as an authorization root.
"""
from __future__ import annotations

import re

SCHEMA = "agent-collab-release/1"
_REQUIRED = ("schema", "Asset-Name", "Asset-SHA256", "Manifest-SHA256")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")          # lowercase-only, canonical
_ASSET_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
# NO SPACE, and no other character GitHub rewrites: GitHub normalizes special
# characters in release-asset filenames, so an asset uploaded as "a b.plugin"
# is stored under a different name than the one the tag SIGNED. The v3 receipt
# check compares the stored name to the signed name, so permitting a rewritten
# character would make a legitimate cut fail as a CONFLICT. Restrict the grammar
# to characters GitHub preserves verbatim.
_TAG_RE = re.compile(r"\Av(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
# Bounds, so oversized input fails cheaply and a tag can never exceed a filesystem
# or ref component limit and then fail deep inside a path/ref operation instead.
_MAX_TAG_LEN = 64
_MAX_MESSAGE_BYTES = 4096
# Windows reserved device names: a file called CON or NUL.plugin is not a file.
_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
)
# \A/\Z, never ^/$: `$` also matches BEFORE a trailing newline, so "v1.0.0\n"
# would pass and become a filename containing a newline. Leading zeros are
# rejected too — "v01.0.0" and "v1.0.0" must not be two names for one release.



# NOT AN AUTHORIZATION ROOT — this module is the message GRAMMAR only. It does not
# bind repository identity, so a tag signed by the same key in another repository
# parses here. Intent binding (repo id, release commit, channel, signer policy)
# lands with the v3 saga; until then no caller may treat a parse result as proof
# that this release was authorized for THIS repository.
class TagContractError(ValueError):
    """The tag message or release commit violates the release contract."""


def validate_tag_name(tag: str) -> str:
    """Reject any tag string before it is used in a path, ref, or command.

    `refs/tags/<tag>` and `refs/tags/revoked-<tag>` are INTENDED to interpolate this,
    so a traversal or ref-injection attempt is stopped at the boundary rather than
    deep inside a filesystem or git operation. (No caller exists yet — see the scope
    note above.)
    """
    if not isinstance(tag, str) or not _TAG_RE.match(tag):
        raise TagContractError(f"tag must be vMAJOR.MINOR.PATCH, got {tag!r}")
    if len(tag) > _MAX_TAG_LEN:
        raise TagContractError(
            f"tag exceeds {_MAX_TAG_LEN} characters; refusing before it reaches a ref or path"
        )
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
    # Bound BEFORE strip/split so oversized input is cheap to reject.
    if len(message.encode("utf-8", "surrogateescape")) > _MAX_MESSAGE_BYTES:
        raise TagContractError(f"tag message exceeds {_MAX_MESSAGE_BYTES} bytes")
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
    # A release asset may be materialized on any consumer platform, so the name
    # must be portable: a trailing dot or a Windows reserved device stem (CON,
    # NUL, COM1, ...) can silently become a different file, or none at all.
    if fields["Asset-Name"].endswith("."):
        raise TagContractError("asset name must not end with a dot (not portable)")
    if fields["Asset-Name"].split(".")[0].upper() in _RESERVED_STEMS:
        raise TagContractError(
            f"asset name uses a reserved device stem: {fields['Asset-Name']!r}"
        )
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
