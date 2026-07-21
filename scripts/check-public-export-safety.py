#!/usr/bin/env python3
"""Audit active files or reachable history before a public source export."""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import stat
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_NAMES = {
    "agent-collab-plugin",
    "gemini-collab",
    "claude-collab",
    "codex-collab",
    "antigravity-collab",
    "codex-tools",
    "glm-worker",
    "grok-worker",
    "grok-collab",
}
EXECUTOR_SOURCES = {
    "codex_exec.py",
    "opencode_exec.py",
    "gemini_review.py",
    "grok_review.py",
}
PROVIDER_BACKEND_PATH_PARTS = {"backend", "mcp-server"}
PRIVATE_PATTERNS = (
    "/Users/",
    "Documents/Claude/Projects",
    "Documents/Codex/agent-collab-workspace",
)
RAW_RECIPE_PATTERNS = (
    "command -v codex",
    "opencode run -m",
    "codex exec --",
    "grok --prompt-file",
)
INTERNAL_PROMPT_PATTERNS = (
    "internal_prompt",
    "prompt_corpus",
    "private_prompt",
    "governance_prompt_template",
)
CREDENTIAL_PATTERNS = (
    "aws_secret_access_key",
    "authorization: bearer",
    "-----begin private key-----",
    "xai_api_key",
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
)
RENAMED_EXECUTOR_MARKERS = (
    b"qualify_exact_binary",
    b"exact_binary_qualification",
    b"provider_credential_isolation",
)
MAX_SCANNED_FILE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_DEPTH = 3
RUNTIME_BUNDLE_REL = Path(
    "plugins/agent-collab/runtime/darwin-arm64/agent-collab-runtime.bundle"
)


def _load_runtime_bundle_contract():
    path = REPO_ROOT / "plugins" / "agent-collab" / "runtime_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "agent_collab_export_runtime_bundle", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime bundle contract cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_bundle = _load_runtime_bundle_contract()
HARMLESS_AUDIT_LITERALS: dict[Path, frozenset[str | bytes]] = {
    Path("scripts/check-public-export-safety.py"): frozenset(
        EXECUTOR_SOURCES
        | set(PRIVATE_PATTERNS)
        | set(RAW_RECIPE_PATTERNS)
        | set(INTERNAL_PROMPT_PATTERNS)
        | set(CREDENTIAL_PATTERNS)
    ),
    Path("tests/test_no_prohibited_claude_cli_backend.py"): frozenset(
        {
            "command -v codex",
            "opencode run -m",
            "grok --prompt-file",
            "codex_exec.py",
            "opencode_exec.py",
        }
    ),
    Path("tests/test_provider_plugin_retirement.py"): frozenset(
        {
            "codex exec --sandbox workspace-write",
            "command -v codex",
            "opencode run -m",
            "scripts/opencode_exec.py",
        }
    ),
    Path("tests/test_public_export_safety.py"): frozenset(
        {
            "codex_exec.py",
            "/Users/",
            "/Users/private/project",
            "/Users/private/tag-message",
            "internal_prompt",
            'PATTERN = "/Users/"\n',
            'PRIVATE = "/Users/private/project"\n',
            'PRIVATE = "/Users/private/project"\n'
            'UNEXPECTED = "/Users/unexpected/operator-home"\n',
            b"internal_prompt\x00private blob",
            b"\xff\x00/Users/private/workspace\x00",
            b"\xff\xfe\x00internal_prompt_corpus\x00AWS_SECRET_ACCESS_KEY\x00",
            b"prefix\x00/Users/private/workspace\x00suffix",
            b"codex_exec.py\x00opencode_exec.py",
            b"/Users/nested/private-workspace",
            "includes internal_prompt and AWS_SECRET_ACCESS_KEY material",
        }
    ),
}
PUBLIC_RELEASE_TAG_RE = re.compile(
    r"^(?:v|v-agent-collab-)(?P<major>\d+)\.\d+\.\d+$"
)
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
REQUIRED_RUNTIME_CONTRACTS = frozenset(
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


@dataclass(frozen=True)
class Violation:
    kind: str
    evidence: str


def _path_violation(path: Path, relative: Path) -> Violation | None:
    if path.is_symlink():
        return Violation("unsafe_symlink", str(relative))
    if any(part in LEGACY_NAMES for part in relative.parts):
        return Violation("legacy_path", str(relative))
    if any(part in PROVIDER_BACKEND_PATH_PARTS for part in relative.parts):
        return Violation("provider_backend_source", str(relative))
    if path.name in EXECUTOR_SOURCES or path.suffix == ".pyc" or "__pycache__" in relative.parts:
        return Violation("executor_source", str(relative))
    return None


def _bytes_contains(data: bytes, pattern: str) -> bool:
    return pattern.encode("utf-8").lower() in data.lower()


def _mask_harmless_audit_literals(data: bytes, relative: Path | None) -> bytes:
    allowed = HARMLESS_AUDIT_LITERALS.get(relative) if relative is not None else None
    if not allowed:
        return data
    try:
        source = data.decode("utf-8")
        tree = ast.parse(source)
    except (UnicodeError, SyntaxError, ValueError):
        return data
    line_offsets: list[int] = []
    offset = 0
    for line in source.splitlines(keepends=True):
        line_offsets.append(offset)
        offset += len(line.encode("utf-8"))
    masked = bytearray(data)
    scanner_declarations = {
        "EXECUTOR_SOURCES",
        "PRIVATE_PATTERNS",
        "RAW_RECIPE_PATTERNS",
        "INTERNAL_PROMPT_PATTERNS",
        "CREDENTIAL_PATTERNS",
        "HARMLESS_AUDIT_LITERALS",
    }
    for node in ast.walk(tree):
        mask_node: ast.AST | None = None
        if isinstance(node, ast.Constant) and node.value in allowed:
            mask_node = node
        elif relative == Path("scripts/check-public-export-safety.py") and isinstance(
            node, (ast.Assign, ast.AnnAssign)
        ):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {target.id for target in targets if isinstance(target, ast.Name)}
            if names.intersection(scanner_declarations):
                mask_node = node.value
        if (
            mask_node is None
            or not hasattr(mask_node, "end_lineno")
            or mask_node.end_lineno is None
            or mask_node.end_col_offset is None
        ):
            continue
        start = line_offsets[mask_node.lineno - 1] + mask_node.col_offset
        end = line_offsets[mask_node.end_lineno - 1] + mask_node.end_col_offset
        for index in range(start, min(end, len(masked))):
            if masked[index] not in {10, 13}:
                masked[index] = 32
    if relative == Path("scripts/check-public-export-safety.py"):
        identifier = b"INTERNAL_PROMPT_PATTERNS"
        masked = bytearray(bytes(masked).replace(identifier, b" " * len(identifier)))
    return bytes(masked)


def _python_semantic_violations(data: bytes, evidence: str) -> list[Violation]:
    try:
        source = data.decode("utf-8")
        tree = ast.parse(source)
    except (UnicodeError, SyntaxError, ValueError):
        return [Violation("python_semantic_unreadable", evidence)]
    assignments: dict[str, ast.AST] = {}
    process_module_aliases: dict[str, str] = {}
    process_function_aliases: set[str] = set()
    process_functions = {
        "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
        "os": {
            "execv",
            "execve",
            "execvp",
            "execvpe",
            "popen",
            "posix_spawn",
            "posix_spawnp",
            "spawnl",
            "spawnle",
            "spawnlp",
            "spawnlpe",
            "spawnv",
            "spawnve",
            "spawnvp",
            "spawnvpe",
            "system",
        },
        "subprocess": {"Popen", "call", "check_call", "check_output", "run"},
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in process_functions:
                    process_module_aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in process_functions:
            for alias in node.names:
                if alias.name in process_functions[node.module]:
                    process_function_aliases.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and value is not None:
                    assignments[target.id] = value

    def static(node: ast.AST, seen: frozenset[str] = frozenset()) -> object | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in assignments and node.id not in seen:
            return static(assignments[node.id], seen | {node.id})
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = static(node.left, seen), static(node.right, seen)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            return None
        if isinstance(node, (ast.List, ast.Tuple)):
            values = [static(item, seen) for item in node.elts]
            return values if all(isinstance(item, str) for item in values) else None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and len(node.args) == 1
        ):
            separator = static(node.func.value, seen)
            values = static(node.args[0], seen)
            if isinstance(separator, str) and isinstance(values, list):
                return separator.join(values)
        return None

    def provider_argv(value: object) -> list[str] | None:
        if isinstance(value, str):
            try:
                return shlex.split(value)
            except ValueError:
                return None
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        return None

    def is_process_launcher(node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id in process_function_aliases
        if not isinstance(node.func, ast.Attribute):
            return False
        owner = node.func.value
        if not isinstance(owner, ast.Name):
            return False
        module = process_module_aliases.get(owner.id)
        return module is not None and node.func.attr in process_functions[module]

    def unwrap_env(argv: list[str]) -> list[str]:
        if not argv or Path(argv[0]).name.lower() != "env":
            return argv
        index = 1
        while index < len(argv):
            token = argv[index]
            if token == "--":
                index += 1
                break
            if token in {"-i", "--ignore-environment", "-0", "--null", "--debug"}:
                index += 1
                continue
            if token in {"-u", "--unset", "-C", "--chdir"}:
                index += 2
                continue
            if token.startswith(("--unset=", "--chdir=")):
                index += 1
                continue
            if token in {"-S", "--split-string"} and index + 1 < len(argv):
                try:
                    split = shlex.split(argv[index + 1])
                except ValueError:
                    return []
                return split + argv[index + 2 :]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
                index += 1
                continue
            break
        return argv[index:]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not is_process_launcher(node):
            continue
        argv_node = node.args[0] if node.args else None
        if argv_node is None:
            for keyword in node.keywords:
                if keyword.arg == "args":
                    argv_node = keyword.value
                    break
        if argv_node is None:
            continue
        argv = provider_argv(static(argv_node))
        if not argv:
            continue
        argv = unwrap_env(argv)
        if not argv:
            continue
        executable = Path(argv[0]).name.lower()
        if executable in {"claude", "codex", "gemini", "grok", "opencode"}:
            return [Violation("raw_provider_recipe", f"{evidence}: constructed argv")]
    return []


def _content_violations(
    data: bytes,
    evidence: str,
    *,
    renamed_candidate: bool,
    mask_path: Path | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    lowered = _mask_harmless_audit_literals(data, mask_path).lower()
    for pattern in PRIVATE_PATTERNS:
        if pattern.encode("utf-8").lower() in lowered:
            violations.append(Violation("private_path", f"{evidence}: {pattern}"))
    for pattern in RAW_RECIPE_PATTERNS:
        if pattern.encode("utf-8").lower() in lowered:
            violations.append(Violation("raw_provider_recipe", f"{evidence}: {pattern}"))
    for pattern in INTERNAL_PROMPT_PATTERNS:
        if pattern.encode("utf-8").lower() in lowered:
            violations.append(Violation("internal_prompt", f"{evidence}: {pattern}"))
    for pattern in CREDENTIAL_PATTERNS:
        if pattern.encode("utf-8").lower() in lowered:
            violations.append(Violation("credential_material", f"{evidence}: {pattern}"))
    for name in EXECUTOR_SOURCES:
        if name.encode("utf-8").lower() in lowered:
            violations.append(Violation("executor_source", f"{evidence}: {name}"))
    python_like = (
        lowered.startswith(b"#!")
        and b"python" in lowered[:128]
        and b"import subprocess" in lowered
    )
    marker_like = any(marker in lowered for marker in RENAMED_EXECUTOR_MARKERS)
    if renamed_candidate and (python_like or marker_like):
        violations.append(Violation("renamed_executor_source", evidence))
    if evidence.lower().endswith(".py") or python_like:
        violations.extend(_python_semantic_violations(data, evidence))
    return violations


@dataclass
class _ArchiveBudget:
    members: int = 0
    total_bytes: int = 0


def _archive_violations(
    data: bytes,
    evidence: str,
    *,
    _depth: int = 0,
    _budget: _ArchiveBudget | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    budget = _budget or _ArchiveBudget()

    def scan_member(name: str, body: bytes, *, mode: int = 0, link: bool = False) -> None:
        pure = Path(name)
        if pure.is_absolute() or ".." in pure.parts or link:
            violations.append(Violation("unsafe_archive_member", f"{evidence}!{name}"))
            return
        if mode & (stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID):
            violations.append(Violation("unsafe_archive_mode", f"{evidence}!{name}"))
        budget.total_bytes += len(body)
        if (
            len(body) > MAX_ARCHIVE_MEMBER_BYTES
            or budget.total_bytes > MAX_ARCHIVE_TOTAL_BYTES
        ):
            violations.append(Violation("archive_limit", f"{evidence}!{name}"))
            return
        virtual = f"{evidence}!{name}"
        member_path = Path(name)
        if any(part in LEGACY_NAMES for part in member_path.parts):
            violations.append(Violation("legacy_path", virtual))
        if any(part in PROVIDER_BACKEND_PATH_PARTS for part in member_path.parts):
            violations.append(Violation("provider_backend_source", virtual))
        if member_path.name in EXECUTOR_SOURCES or member_path.suffix == ".pyc":
            violations.append(Violation("executor_source", virtual))
        violations.extend(
            _content_violations(
                body,
                virtual,
                renamed_candidate=member_path.suffix not in {".py", ".md", ".json", ".yaml", ".yml"},
            )
        )
        violations.extend(
            _archive_violations(
                body,
                virtual,
                _depth=_depth + 1,
                _budget=budget,
            )
        )

    stream = io.BytesIO(data)
    try:
        if zipfile.is_zipfile(stream):
            if _depth > MAX_ARCHIVE_DEPTH:
                return [Violation("archive_limit", f"{evidence}: nesting depth")]
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                infos = archive.infolist()
                budget.members += len(infos)
                if budget.members > MAX_ARCHIVE_MEMBERS:
                    return [Violation("archive_limit", evidence)]
                for info in infos:
                    if info.is_dir():
                        continue
                    mode = (info.external_attr >> 16) & 0xFFFF
                    is_link = stat.S_ISLNK(mode)
                    if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                        violations.append(Violation("archive_limit", f"{evidence}!{info.filename}"))
                        continue
                    try:
                        body = archive.read(info)
                    except (OSError, RuntimeError, zipfile.BadZipFile):
                        violations.append(Violation("archive_unreadable", f"{evidence}!{info.filename}"))
                        continue
                    scan_member(info.filename, body, mode=mode, link=is_link)
            return violations
    except (OSError, RuntimeError, zipfile.BadZipFile):
        return [Violation("archive_unreadable", evidence)]
    stream.seek(0)
    try:
        with tarfile.open(fileobj=stream, mode="r:*") as archive:
            if _depth > MAX_ARCHIVE_DEPTH:
                return [Violation("archive_limit", f"{evidence}: nesting depth")]
            members = archive.getmembers()
            budget.members += len(members)
            if budget.members > MAX_ARCHIVE_MEMBERS:
                return [Violation("archive_limit", evidence)]
            for member in members:
                if member.isdir():
                    continue
                if member.size > MAX_ARCHIVE_MEMBER_BYTES:
                    violations.append(Violation("archive_limit", f"{evidence}!{member.name}"))
                    continue
                extracted = archive.extractfile(member) if member.isfile() else None
                body = extracted.read(MAX_ARCHIVE_MEMBER_BYTES + 1) if extracted else b""
                scan_member(
                    member.name,
                    body,
                    mode=member.mode,
                    link=member.issym() or member.islnk() or not member.isfile(),
                )
        return violations
    except (OSError, tarfile.TarError):
        pass

    if data.startswith(b"\x1f\x8b"):
        if _depth > MAX_ARCHIVE_DEPTH:
            return [Violation("archive_limit", f"{evidence}: nesting depth")]
        budget.members += 1
        if budget.members > MAX_ARCHIVE_MEMBERS:
            return [Violation("archive_limit", evidence)]
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as compressed:
                body = compressed.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
        except (EOFError, OSError):
            return [Violation("archive_unreadable", f"{evidence}!gzip")]
        scan_member("gzip", body)
        return violations
    return []


def _runtime_contract_violation(root: Path, relative: Path, data: bytes) -> Violation | None:
    runtime_root = Path("plugins/agent-collab/runtime")
    try:
        relative.relative_to(runtime_root)
    except ValueError:
        return None
    if relative.parent != RUNTIME_BUNDLE_REL:
        return Violation("unmanifested_runtime", str(relative))

    manifest_path = root / "plugins" / "agent-collab" / "runtime-manifest.json"
    signing_policy_path = root / "plugins" / "agent-collab" / "signing_policy.py"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return Violation("unmanifested_runtime", str(relative))
    try:
        policy_tree = ast.parse(signing_policy_path.read_text(encoding="utf-8"))
        pinned_values = [
            node.value.value
            for node in policy_tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            if isinstance(target, ast.Name)
            and target.id == "EXPECTED_DEVELOPER_ID_TEAM"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ]
    except (OSError, SyntaxError, ValueError):
        pinned_values = []
    pinned_team = pinned_values[0] if len(pinned_values) == 1 else ""

    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {
            "schema_version",
            "protocol_version",
            "contract_version",
            "broker_protocol_version",
            "channel",
            "artifacts",
        }
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 3
        or type(manifest.get("protocol_version")) is not int
        or manifest["protocol_version"] != 2
        or type(manifest.get("contract_version")) is not int
        or manifest["contract_version"] != 3
        or type(manifest.get("broker_protocol_version")) is not int
        or manifest["broker_protocol_version"] != 2
        or manifest.get("channel") != "production"
        or not isinstance(manifest.get("artifacts"), list)
        or len(manifest["artifacts"]) != 1
        or not isinstance(manifest["artifacts"][0], dict)
    ):
        return Violation("unmanifested_runtime", str(relative))
    item = manifest["artifacts"][0]
    signing = item.get("signing")
    contracts = item.get("contracts")
    contract_rows: list[tuple[str, str]] = []
    if isinstance(contracts, list):
        for entry in contracts:
            if not isinstance(entry, dict) or set(entry) != {"route", "action"}:
                contract_rows = []
                break
            route, action = entry.get("route"), entry.get("action")
            if not isinstance(route, str) or not isinstance(action, str):
                contract_rows = []
                break
            contract_rows.append((route, action))
    try:
        records = runtime_bundle.validate_file_records(item.get("files"))
        bundle_identity = runtime_bundle.compute_bundle_identity(records)
    except runtime_bundle.BundleContractError:
        return Violation("unmanifested_runtime", str(relative))
    identity = signing.get("identity") if isinstance(signing, dict) else None
    identity_match = (
        re.fullmatch(
            r"Developer ID Application: [^\r\n]{1,160} \(([A-Z0-9]{10})\)",
            identity,
        )
        if isinstance(identity, str)
        else None
    )
    if (
        set(item)
        != {
            "platform",
            "arch",
            "kind",
            "minimum_macos",
            "path",
            "entrypoint",
            "size",
            "sha256",
            "provider_runtime_version",
            "route_contract_version",
            "signing",
            "files",
            "contracts",
        }
        or item.get("platform") != "darwin"
        or item.get("arch") != "arm64"
        or item.get("kind") != "standalone_bundle"
        or item.get("minimum_macos") != "14.0"
        or item.get("path")
        != "runtime/darwin-arm64/agent-collab-runtime.bundle"
        or item.get("entrypoint") != runtime_bundle.ENTRYPOINT_NAME
        or item.get("provider_runtime_version") != "2.0.0"
        or item.get("route_contract_version") != 2
        or type(item.get("size")) is not int
        or item["size"] != sum(record["size"] for record in records)
        or item.get("sha256") != bundle_identity
        or not isinstance(signing, dict)
        or set(signing)
        != {
            "mode",
            "identity",
            "team_id",
            "require_notarization",
            "hardened_runtime",
            "secure_timestamp",
        }
        or signing.get("mode") != "developer_id"
        or identity_match is None
        or not isinstance(signing.get("team_id"), str)
        or not _TEAM_ID_RE.fullmatch(signing["team_id"])
        or identity_match.group(1) != signing["team_id"]
        or not _TEAM_ID_RE.fullmatch(pinned_team)
        or signing["team_id"] != pinned_team
        or signing.get("require_notarization") is not True
        or signing.get("hardened_runtime") is not True
        or signing.get("secure_timestamp") is not True
        or any(
            record["signing_profile"] != "production_developer_id"
            for record in records
        )
        or frozenset(contract_rows) != REQUIRED_RUNTIME_CONTRACTS
        or len(contract_rows) != len(REQUIRED_RUNTIME_CONTRACTS)
    ):
        return Violation("unmanifested_runtime", str(relative))

    bundle = root / RUNTIME_BUNDLE_REL
    by_name = {record["path"]: record for record in records}
    record = by_name.get(relative.name)
    try:
        bundle_info = bundle.lstat()
        observed_names = sorted(path.name for path in bundle.iterdir())
        member_info = (root / relative).lstat()
    except OSError:
        return Violation("unmanifested_runtime", str(relative))
    if (
        record is None
        or observed_names != [item["path"] for item in records]
        or not stat.S_ISDIR(bundle_info.st_mode)
        or stat.S_ISLNK(bundle_info.st_mode)
        # Scans the checked-out git tree (--active-tree); modes are 0o755/0o700.
        # Content is pinned by size + sha256 below.
        or not runtime_bundle.source_mode_ok(bundle_info.st_mode)
        or not stat.S_ISREG(member_info.st_mode)
        or stat.S_ISLNK(member_info.st_mode)
        or member_info.st_nlink != 1
        or not runtime_bundle.source_mode_ok(member_info.st_mode)
        or record["size"] != len(data)
        or record["sha256"] != hashlib.sha256(data).hexdigest()
    ):
        return Violation("unmanifested_runtime", str(relative))
    return None
def scan_active_tree(root: Path) -> list[Violation]:
    root = root.resolve()
    violations: list[Violation] = []
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
        check=False,
    )
    if tracked.returncode == 0:
        relative_paths = [
            Path(raw.decode("utf-8", errors="surrogateescape"))
            for raw in tracked.stdout.split(b"\0")
            if raw
        ]
    else:
        relative_paths = []
        for current, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if name != ".git"]
            base = Path(current)
            relative_paths.extend((base / name).relative_to(root) for name in files)

    for relative in relative_paths:
        path = root / relative
        if relative == Path(".git"):
            continue
        path_issue = _path_violation(path, relative)
        if path_issue:
            violations.append(path_issue)
            continue
        try:
            data = path.read_bytes()
        except OSError:
            violations.append(Violation("unreadable", str(relative)))
            continue
        if len(data) > MAX_SCANNED_FILE_BYTES:
            violations.append(Violation("file_limit", str(relative)))
            continue
        runtime_issue = _runtime_contract_violation(root, relative, data)
        if runtime_issue:
            violations.append(runtime_issue)
        violations.extend(
            _content_violations(
                data,
                str(relative),
                renamed_candidate=relative.suffix not in {".py", ".md", ".json", ".yaml", ".yml"}
                and relative.parent != RUNTIME_BUNDLE_REL,
                mask_path=relative,
            )
        )
        violations.extend(_archive_violations(data, str(relative)))
    return sorted(set(violations), key=lambda item: (item.kind, item.evidence))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
    )


def scan_history(root: Path) -> list[Violation]:
    root = root.resolve()
    violations: list[Violation] = []
    commits = _git(root, "rev-list", "--all")
    if commits.returncode != 0:
        return [Violation("history_unreadable", commits.stderr.strip())]
    blob_paths: dict[str, set[Path]] = {}

    def record_tree(object_id: str, evidence_prefix: str) -> None:
        tree = _git_bytes(root, "ls-tree", "-r", "-z", "--full-tree", object_id)
        if tree.returncode != 0:
            violations.append(
                Violation(
                    "history_unreadable",
                    f"{evidence_prefix}: {tree.stderr.decode('utf-8', errors='replace').strip()}",
                )
            )
            return
        for record in tree.stdout.split(b"\0"):
            if not record:
                continue
            try:
                metadata, raw_name = record.split(b"\t", 1)
                mode, object_type, object_id = metadata.decode("ascii").split()
                name = raw_name.decode("utf-8", errors="surrogateescape")
            except (UnicodeError, ValueError):
                violations.append(Violation("history_unreadable", evidence_prefix))
                continue
            path = Path(name)
            if mode not in {"100644", "100755"} or object_type != "blob":
                violations.append(
                    Violation(
                        "history_unsafe_mode", f"{evidence_prefix}:{mode}:{name}"
                    )
                )
            if object_type == "blob":
                blob_paths.setdefault(object_id, set()).add(path)
            if any(part in LEGACY_NAMES for part in path.parts):
                violations.append(Violation("legacy_history", name))
            if any(part in PROVIDER_BACKEND_PATH_PARTS for part in path.parts):
                violations.append(Violation("provider_backend_history", name))
            if path.name in EXECUTOR_SOURCES or path.suffix == ".pyc":
                violations.append(Violation("executor_history", name))

    for commit in commits.stdout.splitlines():
        record_tree(commit, commit)

    refs = _git(root, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(objecttype)")
    if refs.returncode != 0:
        violations.append(Violation("history_unreadable", refs.stderr.strip()))
    else:
        inspected: set[tuple[str, str, str, bool]] = set()

        def inspect_ref_object(
            refname: str,
            object_id: str,
            object_type: str,
            *,
            release_tag: bool,
            top_level: bool,
        ) -> None:
            key = (refname, object_id, object_type, top_level)
            if key in inspected:
                return
            inspected.add(key)
            if object_type == "commit":
                return
            if object_type == "tree":
                record_tree(object_id, refname)
                return
            if object_type == "blob":
                blob_paths.setdefault(object_id, set()).add(
                    Path(".git-ref-objects") / refname
                )
                return
            if object_type != "tag":
                violations.append(
                    Violation("history_unreadable", f"{refname}:{object_id}:{object_type}")
                )
                return
            raw_tag = _git_bytes(root, "cat-file", "tag", object_id)
            if raw_tag.returncode != 0:
                violations.append(
                    Violation("history_unreadable", f"{refname}:{object_id}:tag")
                )
                return
            violations.extend(
                _content_violations(
                    raw_tag.stdout,
                    f"{refname}:{object_id}:tag-message",
                    renamed_candidate=False,
                )
            )
            header, separator, _message = raw_tag.stdout.partition(b"\n\n")
            fields: dict[bytes, bytes] = {}
            if separator:
                for line in header.splitlines():
                    key_value = line.split(b" ", 1)
                    if len(key_value) == 2:
                        fields[key_value[0]] = key_value[1]
            target_raw = fields.get(b"object", b"")
            declared_type_raw = fields.get(b"type", b"")
            declared_tag_raw = fields.get(b"tag", b"")
            try:
                target = target_raw.decode("ascii")
                declared_type = declared_type_raw.decode("ascii")
                declared_tag = declared_tag_raw.decode("utf-8")
            except UnicodeError:
                target = declared_type = declared_tag = ""
            actual = _git(root, "cat-file", "-t", target) if target else None
            actual_type = (
                actual.stdout.strip()
                if actual is not None and actual.returncode == 0
                else ""
            )
            expected_tag = refname.removeprefix("refs/tags/")
            if release_tag and top_level and (
                declared_type != "commit"
                or actual_type != "commit"
                or declared_tag != expected_tag
            ):
                violations.append(Violation("invalid_release_ref", refname))
            if not target or not actual_type or declared_type != actual_type:
                violations.append(
                    Violation("history_unreadable", f"{refname}:{object_id}:tag-target")
                )
                return
            inspect_ref_object(
                refname,
                target,
                actual_type,
                release_tag=release_tag,
                top_level=False,
            )

        for line in refs.stdout.splitlines():
            try:
                refname, object_id, object_type = line.split("\t", 2)
            except ValueError:
                violations.append(Violation("history_unreadable", line))
                continue
            is_tag = refname.startswith("refs/tags/")
            tag_name = refname.removeprefix("refs/tags/") if is_tag else ""
            match = PUBLIC_RELEASE_TAG_RE.fullmatch(tag_name) if is_tag else None
            release_tag = bool(match is not None and int(match.group("major")) >= 3)
            if is_tag and not release_tag:
                violations.append(Violation("legacy_release_ref", tag_name))
            if is_tag and release_tag and object_type != "tag":
                violations.append(Violation("invalid_release_ref", refname))
            if not is_tag and object_type != "commit":
                violations.append(
                    Violation(
                        "history_noncommit_ref",
                        f"{refname}:{object_id}:{object_type}",
                    )
                )
            inspect_ref_object(
                refname,
                object_id,
                object_type,
                release_tag=release_tag,
                top_level=True,
            )

    object_ids = sorted(blob_paths)
    if object_ids:
        batch = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            ],
            input="\n".join(object_ids) + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if batch.returncode != 0:
            violations.append(Violation("history_unreadable", batch.stderr.strip()))
        else:
            sizes: dict[str, int] = {}
            for line in batch.stdout.splitlines():
                try:
                    object_id, object_type, raw_size = line.split()
                    if object_type == "blob":
                        sizes[object_id] = int(raw_size)
                except ValueError:
                    violations.append(Violation("history_unreadable", line))
            for object_id in object_ids:
                paths = sorted(blob_paths[object_id], key=str)
                scan_paths = paths
                renamed_paths = [
                    path
                    for path in scan_paths
                    if path.suffix not in {".py", ".md", ".json", ".yaml", ".yml"}
                    and path.parent != RUNTIME_BUNDLE_REL
                ]
                evidence_path = renamed_paths[0] if renamed_paths else scan_paths[0]
                size = sizes.get(object_id)
                if size is None:
                    violations.append(Violation("history_unreadable", object_id))
                    continue
                if size > MAX_SCANNED_FILE_BYTES:
                    violations.append(
                        Violation("file_limit", f"{object_id}:{evidence_path}")
                    )
                    continue
                blob = _git_bytes(root, "cat-file", "blob", object_id)
                if blob.returncode != 0 or len(blob.stdout) != size:
                    violations.append(
                        Violation("history_unreadable", f"{object_id}:{evidence_path}")
                    )
                    continue
                evidence = f"{object_id}:{evidence_path}"
                violations.extend(
                    _content_violations(
                        blob.stdout,
                        evidence,
                        renamed_candidate=bool(renamed_paths),
                        mask_path=(evidence_path if len(scan_paths) == 1 else None),
                    )
                )
                violations.extend(_archive_violations(blob.stdout, evidence))
    metadata = _git(
        root,
        "log",
        "--all",
        "--format=%H%x1f%an%x1f%ae%x1f%B%x1e",
    )
    if metadata.returncode == 0:
        for record in metadata.stdout.split("\x1e"):
            if not record.strip():
                continue
            fields = record.split("\x1f", 3)
            if len(fields) == 4:
                commit, _author, _email, message = fields
                violations.extend(
                    _content_violations(
                        message.encode("utf-8", errors="surrogateescape"),
                        f"{commit.strip()}:commit-message",
                        renamed_candidate=False,
                    )
                )
            for pattern in PRIVATE_PATTERNS:
                if pattern in record:
                    commit = record.split("\x1f", 1)[0].strip()
                    violations.append(
                        Violation("private_provenance", f"{commit}: {pattern}")
                    )
    return sorted(set(violations), key=lambda item: (item.kind, item.evidence))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--active-tree", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)
    if not args.active_tree and not args.history:
        parser.error("select --active-tree and/or --history")
    violations: list[Violation] = []
    if args.active_tree:
        violations.extend(scan_active_tree(args.export_root))
    if args.history:
        violations.extend(scan_history(args.export_root))
    for item in violations:
        print(f"FAIL [{item.kind}] {item.evidence}")
    if violations:
        print("RESULT: UNSAFE FOR PUBLIC EXPORT")
        return 1
    print("RESULT: SAFE FOR REQUESTED PUBLIC EXPORT CHECKS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
