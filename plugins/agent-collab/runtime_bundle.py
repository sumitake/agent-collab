"""Closed identity and filesystem verification for the standalone provider bundle."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
from typing import Any, Callable, Dict, Mapping, Sequence, Tuple
import unicodedata


class BundleContractError(ValueError):
    """Fixed-value sentinel for a closed runtime-bundle contract failure."""


IDENTITY_DOMAIN = b"agent-collab-runtime-bundle\0v1\0"
MAX_BUNDLE_FILES = 64
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PATH_BYTES = 255
ENTRYPOINT_NAME = "agent-collab-runtime"
INSTALL_MODE = 0o500
MINIMUM_MACOS = "14.0"

_FILE_KEYS = frozenset((
    "architecture",
    "install_mode",
    "macho_type",
    "minimum_macos",
    "path",
    "role",
    "sha256",
    "signing_profile",
    "size",
))
_INSPECTION_KEYS = frozenset((
    "architecture", "macho_type", "minimum_macos", "signing_profile",
))
_ROLE_CODES = {"entrypoint": 1, "runtime_library": 2}
_MACHO_TYPE_CODES = {"executable": 1, "dylib": 2, "bundle": 3}
_ARCHITECTURE_CODES = {"arm64": 1}
_SIGNING_PROFILES = frozenset((
    "development_adhoc", "production_developer_id",
))
_SLASH_CONFUSABLES = frozenset((
    "\\",
    "/",
    "\u2044",  # fraction slash
    "\u2215",  # division slash
    "\u29f5",  # reverse solidus operator
    "\u29f8",  # big solidus
    "\ufe68",  # small reverse solidus
    "\uff0f",  # fullwidth solidus
    "\uff3c",  # fullwidth reverse solidus
))
_JSON_MAX_DEPTH = 64
_JSON_MAX_NODES = 100_000


def _raise(message: str) -> None:
    raise BundleContractError(message)


def _reject_json_constant(_value: str) -> None:
    _raise("runtime manifest contains a non-finite number")


def _reject_json_float(_value: str) -> None:
    _raise("runtime manifest contains a floating-point number")


def _closed_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, child in pairs:
        if type(key) is not str or key in value:
            _raise("runtime manifest contains a duplicate or invalid key")
        value[key] = child
    return value


def _validate_json_tree(root: Any) -> None:
    """Require an exact built-in JSON tree with bounded depth and node count."""

    stack = [(root, 0)]
    seen = 0
    while stack:
        value, depth = stack.pop()
        seen += 1
        if seen > _JSON_MAX_NODES or depth > _JSON_MAX_DEPTH:
            _raise("runtime manifest JSON exceeds its structural bound")
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str:
                    _raise("runtime manifest contains an invalid key")
                _validate_unicode_scalar_text(key, "runtime manifest key")
                stack.append((child, depth + 1))
        elif type(value) is list:
            for child in value:
                stack.append((child, depth + 1))
        elif type(value) is str:
            _validate_unicode_scalar_text(value, "runtime manifest string")
        elif type(value) in (int, bool) or value is None:
            continue
        else:
            _raise("runtime manifest contains a non-JSON value")


def load_closed_json_object(raw: bytes) -> Dict[str, Any]:
    """Decode one bounded JSON object with duplicate/non-finite/float rejection."""

    if type(raw) is not bytes or not raw or len(raw) > MAX_MANIFEST_BYTES:
        _raise("runtime manifest bytes are invalid")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except BundleContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise BundleContractError("runtime manifest JSON is invalid") from None
    if type(value) is not dict:
        _raise("runtime manifest root is not an object")
    _validate_json_tree(value)
    return value


def _validate_unicode_scalar_text(value: str, label: str) -> None:
    if type(value) is not str:
        _raise(f"{label} is not a string")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise BundleContractError(f"{label} is not valid UTF-8") from None
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _raise(f"{label} contains a surrogate")


def _exact_string(value: Any, label: str) -> str:
    if type(value) is not str:
        _raise(f"runtime bundle {label} is invalid")
    _validate_unicode_scalar_text(value, f"runtime bundle {label}")
    return value


def _exact_integer(value: Any, label: str) -> int:
    if type(value) is not int:
        _raise(f"runtime bundle {label} is invalid")
    return value


def _validate_path(value: Any) -> Tuple[str, bytes, str]:
    path = _exact_string(value, "path")
    if not path or path in (".", "..") or unicodedata.normalize("NFC", path) != path:
        _raise("runtime bundle path is not normalized")
    if any(character in _SLASH_CONFUSABLES for character in path):
        _raise("runtime bundle path contains a separator or confusable")
    if any(unicodedata.category(character).startswith("C") for character in path):
        _raise("runtime bundle path contains a control character")
    try:
        encoded = path.encode("utf-8")
    except UnicodeError:
        raise BundleContractError("runtime bundle path is not valid UTF-8") from None
    if not encoded or len(encoded) > MAX_PATH_BYTES:
        _raise("runtime bundle path length is invalid")
    representation = unicodedata.normalize("NFKC", path).casefold()
    return path, encoded, representation


def _validate_digest(value: Any) -> str:
    digest = _exact_string(value, "SHA-256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        _raise("runtime bundle SHA-256 is invalid")
    return digest


def validate_file_records(records: Any) -> Tuple[Dict[str, Any], ...]:
    """Validate the closed file-record array without accepting coercions."""

    if type(records) not in (list, tuple):
        _raise("runtime bundle files are not a closed array")
    if not records or len(records) > MAX_BUNDLE_FILES:
        _raise("runtime bundle file count is invalid")

    normalized = []
    expected_sort = []
    representations = set()
    total_size = 0
    entrypoints = 0
    selected_profile = None

    for record in records:
        if type(record) is not dict or frozenset(record) != _FILE_KEYS:
            _raise("runtime bundle file record schema is invalid")
        path, path_bytes, representation = _validate_path(record["path"])
        if representation in representations:
            _raise("runtime bundle has a duplicate path representation")
        representations.add(representation)
        expected_sort.append(path_bytes)

        role = _exact_string(record["role"], "role")
        if role not in _ROLE_CODES:
            _raise("runtime bundle role is invalid")
        mode = _exact_integer(record["install_mode"], "install mode")
        if mode != INSTALL_MODE:
            _raise("runtime bundle install mode is invalid")
        size = _exact_integer(record["size"], "size")
        if size < 0 or size > MAX_BUNDLE_BYTES:
            _raise("runtime bundle file size is invalid")
        total_size += size
        if total_size > MAX_BUNDLE_BYTES:
            _raise("runtime bundle installed size exceeds its budget")
        digest = _validate_digest(record["sha256"])
        macho_type = _exact_string(record["macho_type"], "Mach-O type")
        architecture = _exact_string(record["architecture"], "architecture")
        minimum_macos = _exact_string(record["minimum_macos"], "minimum macOS")
        profile = _exact_string(record["signing_profile"], "signing profile")

        if role == "entrypoint":
            entrypoints += 1
            if path != ENTRYPOINT_NAME or macho_type != "executable":
                _raise("runtime bundle entrypoint record is invalid")
        elif macho_type not in ("dylib", "bundle"):
            _raise("runtime bundle library record is invalid")
        if architecture != "arm64":
            _raise("runtime bundle architecture is invalid")
        if minimum_macos != MINIMUM_MACOS:
            _raise("runtime bundle minimum macOS is invalid")
        if profile not in _SIGNING_PROFILES:
            _raise("runtime bundle signing profile is invalid")
        if selected_profile is None:
            selected_profile = profile
        elif profile != selected_profile:
            _raise("runtime bundle signing profiles are inconsistent")

        normalized.append({
            "path": path,
            "role": role,
            "install_mode": mode,
            "size": size,
            "sha256": digest,
            "macho_type": macho_type,
            "architecture": architecture,
            "minimum_macos": minimum_macos,
            "signing_profile": profile,
        })

    if entrypoints != 1:
        _raise("runtime bundle must contain exactly one entrypoint")
    if expected_sort != sorted(expected_sort):
        _raise("runtime bundle files are not sorted by exact UTF-8 path bytes")
    return tuple(normalized)


def encode_bundle_identity(records: Any) -> bytes:
    """Encode the validated records using the contract-v3 identity grammar."""

    validated = validate_file_records(records)
    encoded = bytearray(IDENTITY_DOMAIN)
    encoded.extend(struct.pack(">I", len(validated)))
    for record in validated:
        path = record["path"].encode("utf-8")
        encoded.extend(struct.pack(">I", len(path)))
        encoded.extend(path)
        encoded.extend(struct.pack(">B", _ROLE_CODES[record["role"]]))
        encoded.extend(struct.pack(">H", record["install_mode"]))
        encoded.extend(struct.pack(">Q", record["size"]))
        encoded.extend(bytes.fromhex(record["sha256"]))
        encoded.extend(struct.pack(">B", _MACHO_TYPE_CODES[record["macho_type"]]))
        encoded.extend(struct.pack(">B", _ARCHITECTURE_CODES[record["architecture"]]))
    return bytes(encoded)


def compute_bundle_identity(records: Any) -> str:
    return hashlib.sha256(encode_bundle_identity(records)).hexdigest()


def _stat_identity(info: os.stat_result) -> Tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _hash_descriptor(descriptor: int, expected_size: int) -> str:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
    except OSError:
        raise BundleContractError("runtime bundle member is not seekable") from None
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        try:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        except OSError:
            raise BundleContractError("runtime bundle member could not be read") from None
        if not chunk:
            _raise("runtime bundle member changed size")
        digest.update(chunk)
        remaining -= len(chunk)
    try:
        if os.read(descriptor, 1):
            _raise("runtime bundle member changed size")
    except OSError:
        raise BundleContractError("runtime bundle member could not be read") from None
    return digest.hexdigest()


def _validate_inspection(value: Any, record: Mapping[str, Any]) -> None:
    if type(value) is not dict or frozenset(value) != _INSPECTION_KEYS:
        _raise("runtime bundle member inspection schema is invalid")
    for key in _INSPECTION_KEYS:
        if type(value[key]) is not str or value[key] != record[key]:
            _raise("runtime bundle member inspection changed")


def tolerant_mode_ok(mode: int) -> bool:
    """Safe-envelope mode predicate for a GIT-DISTRIBUTED source tree.

    A git checkout cannot preserve the build store's `0o500`: it yields `0o755`
    (umask 022) or `0o700` (umask 077), and host plugin managers re-extract and
    normalize modes on install and every autoUpdate/restart. The tamper guarantee
    is the whole-bundle + per-member digest and Developer-ID signature — NOT the
    mode (the root predicate has said so, operator-approved, since this bundle
    shipped). Exact `0o500` was never a same-UID TOCTOU boundary either: the owner
    could always chmod it, and a different UID cannot write into an owner-only tree.

    This predicate is the SINGLE source of that rule, shared by the bundle root,
    the (tolerant) member check, and the release/export/archive-source gates that
    now run against the checked-out git tree — so tolerance can never drift across
    files. It requires owner read+execute (correct for the all-Mach-O members and
    the traversable directories), and rejects the actual attack vectors: any
    group/other WRITE and any setuid/setgid/sticky bit. It accepts `0o500`, `0o700`
    and `0o755` (and other read/execute combinations in that envelope) while
    rejecting `0o775` / `0o757` / `0o777` and special-bit modes.

    NOTE (reviewer finding 7): every current member is a `0o500` Mach-O executable,
    so requiring owner-execute is correct for all of them. A future NON-executable
    data member would need a role-aware predicate and a manifest schema change
    before it could be recorded — it must not silently ride this envelope.
    """
    perms = stat.S_IMODE(mode)
    return (
        (perms & 0o500) == 0o500  # owner read + execute present
        and (perms & 0o022) == 0  # no group/other WRITE
        and (perms & 0o7000) == 0  # no setuid / setgid / sticky
    )


def _bundle_root_mode_ok(mode: int) -> bool:
    """The bundle root uses the shared safe-envelope predicate (see tolerant_mode_ok)."""
    return tolerant_mode_ok(mode)


def verify_bundle_tree(
    root: Path,
    records: Any,
    *,
    inspector: Callable[[Path], Dict[str, str]],
    tolerant: bool = False,
) -> str:
    """Verify one closed standalone bundle without following filesystem links.

    `tolerant` selects the MODE check only. False (default) requires each member's
    mode to equal the manifest `install_mode` exactly — used for the privately
    extracted broker store, where the exact `0o500` is achievable and worth keeping
    as a publication-drift invariant. True accepts the shared safe envelope
    (`tolerant_mode_ok`) — used for the git-installed plugin tree, whose modes are
    normalized to `0o755`/`0o700` by the checkout and cannot be `0o500`. Every other
    check — regular-file type, no symlink, `uid == geteuid`, `nlink == 1`, size,
    stat identity, per-member SHA-256, and the Mach-O/signature inspection — is
    identical in both modes; tolerance touches nothing but the permission bits."""

    if not isinstance(root, Path) or not callable(inspector):
        _raise("runtime bundle verifier arguments are invalid")
    validated = validate_file_records(records)
    expected_names = tuple(record["path"] for record in validated)
    by_name = {record["path"]: record for record in validated}
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)

    try:
        root_descriptor = os.open(root, flags)
    except OSError:
        raise BundleContractError("runtime bundle root is invalid") from None
    try:
        try:
            root_before = os.fstat(root_descriptor)
            lexical_root = root.lstat()
        except OSError:
            raise BundleContractError("runtime bundle root is invalid") from None
        if (
            not stat.S_ISDIR(root_before.st_mode)
            or stat.S_ISLNK(lexical_root.st_mode)
            or _stat_identity(root_before) != _stat_identity(lexical_root)
            or root_before.st_uid != os.geteuid()
            or not _bundle_root_mode_ok(root_before.st_mode)
        ):
            _raise("runtime bundle root is unsafe")
        try:
            names = os.listdir(root_descriptor)
        except OSError:
            raise BundleContractError("runtime bundle could not be enumerated") from None
        if any(type(name) is not str for name in names):
            _raise("runtime bundle member name is invalid")
        if tuple(sorted(names, key=lambda name: name.encode("utf-8"))) != expected_names:
            _raise("runtime bundle membership changed")

        for name in expected_names:
            record = by_name[name]
            member_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            member_flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                descriptor = os.open(name, member_flags, dir_fd=root_descriptor)
            except OSError:
                raise BundleContractError("runtime bundle member is invalid") from None
            try:
                try:
                    before = os.fstat(descriptor)
                    lexical_before = os.stat(
                        name, dir_fd=root_descriptor, follow_symlinks=False,
                    )
                except OSError:
                    raise BundleContractError("runtime bundle member is invalid") from None
                if (
                    not stat.S_ISREG(before.st_mode)
                    or stat.S_ISLNK(lexical_before.st_mode)
                    or before.st_uid != os.geteuid()
                    or before.st_nlink != 1
                    or (
                        not tolerant_mode_ok(before.st_mode)
                        if tolerant
                        else stat.S_IMODE(before.st_mode) != record["install_mode"]
                    )
                    or before.st_size != record["size"]
                    or _stat_identity(before) != _stat_identity(lexical_before)
                ):
                    _raise("runtime bundle member metadata changed")
                if _hash_descriptor(descriptor, record["size"]) != record["sha256"]:
                    _raise("runtime bundle member digest changed")

                member_path = root / name
                try:
                    inspection = inspector(member_path)
                except BundleContractError:
                    raise
                except Exception:
                    raise BundleContractError(
                        "runtime bundle member inspection failed"
                    ) from None
                _validate_inspection(inspection, record)

                try:
                    after = os.fstat(descriptor)
                    lexical_after = os.stat(
                        name, dir_fd=root_descriptor, follow_symlinks=False,
                    )
                except OSError:
                    raise BundleContractError("runtime bundle member changed") from None
                if (
                    _stat_identity(after) != _stat_identity(before)
                    or _stat_identity(lexical_after) != _stat_identity(before)
                    or _hash_descriptor(descriptor, record["size"]) != record["sha256"]
                ):
                    _raise("runtime bundle member changed during inspection")
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

        try:
            root_after = os.fstat(root_descriptor)
            final_names = os.listdir(root_descriptor)
        except OSError:
            raise BundleContractError("runtime bundle root changed") from None
        if (
            _stat_identity(root_after) != _stat_identity(root_before)
            or tuple(sorted(final_names, key=lambda name: name.encode("utf-8")))
            != expected_names
        ):
            _raise("runtime bundle root changed during verification")
        return compute_bundle_identity(validated)
    finally:
        try:
            os.close(root_descriptor)
        except OSError:
            pass


__all__ = [
    "BundleContractError",
    "ENTRYPOINT_NAME",
    "IDENTITY_DOMAIN",
    "INSTALL_MODE",
    "MAX_BUNDLE_BYTES",
    "MAX_BUNDLE_FILES",
    "MINIMUM_MACOS",
    "compute_bundle_identity",
    "encode_bundle_identity",
    "load_closed_json_object",
    "tolerant_mode_ok",
    "validate_file_records",
    "verify_bundle_tree",
]
