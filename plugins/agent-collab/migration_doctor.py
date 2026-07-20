#!/usr/bin/env python3
"""Provider-free migration inventory and unified-package readiness report."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    tomllib = None


PLUGIN_ROOT = Path(__file__).resolve().parent
LEGACY_PACKAGES = (
    "agent-collab-plugin",
    "gemini-collab",
    "grok-collab",
    "claude-collab",
    "codex-collab",
    "antigravity-collab",
    "codex-tools",
    "glm-worker",
    "grok-worker",
)
_TABLE_HEADER = re.compile(
    r"^\[(?P<body>[^\[\]\r\n]+)\][ \t]*(?:#.*)?$"
)
_ARRAY_TABLE_HEADER = re.compile(
    r"^\[\[(?P<body>[^\[\]\r\n]+)\]\][ \t]*(?:#.*)?$"
)
_PLUGIN_TABLE = re.compile(
    r'^plugins[ \t]*\.[ \t]*"(?P<identity>[A-Za-z0-9][A-Za-z0-9._-]*(?:@[A-Za-z0-9][A-Za-z0-9._-]*)?)"$'
)
_PLUGIN_ENABLED = re.compile(r"^enabled[ \t]*=[ \t]*(?P<value>true|false)[ \t]*(?:#.*)?$")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_BASIC_KEY_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
}


def _decode_toml_basic_key(candidate: str) -> str:
    """Decode one single-line TOML basic-string key segment."""

    decoded: list[str] = []
    index = 1
    while index < len(candidate):
        character = candidate[index]
        if character == '"':
            return "".join(decoded)
        if character != "\\":
            codepoint = ord(character)
            if (codepoint < 0x20 and character != "\t") or codepoint == 0x7F:
                raise ValueError("unsupported TOML key")
            decoded.append(character)
            index += 1
            continue
        index += 1
        if index >= len(candidate):
            raise ValueError("unterminated TOML key")
        escape = candidate[index]
        if escape in _BASIC_KEY_ESCAPES:
            decoded.append(_BASIC_KEY_ESCAPES[escape])
            index += 1
            continue
        if escape not in {"u", "U"}:
            raise ValueError("unsupported TOML key")
        width = 4 if escape == "u" else 8
        digits = candidate[index + 1 : index + 1 + width]
        if len(digits) != width or any(
            character not in "0123456789abcdefABCDEF" for character in digits
        ):
            raise ValueError("unsupported TOML key")
        codepoint = int(digits, 16)
        if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            raise ValueError("unsupported TOML key")
        decoded.append(chr(codepoint))
        index += width + 1
    raise ValueError("unterminated TOML key")


def _first_toml_key_segment(text: str) -> str:
    """Decode only the first TOML key segment needed for namespace checks."""

    candidate = text.lstrip()
    if not candidate:
        raise ValueError("empty TOML key")
    if candidate[0] == '"':
        return _decode_toml_basic_key(candidate)
    if candidate[0] == "'":
        closing = candidate.find("'", 1)
        if closing == -1:
            raise ValueError("unterminated TOML key")
        return candidate[1:closing]
    match = _BARE_KEY.match(candidate)
    if match is None:
        raise ValueError("unsupported TOML key")
    return match.group(0)


def _assignment_rhs(text: str) -> str | None:
    """Return the RHS of the first unquoted TOML assignment operator."""

    quote: str | None = None
    escaped = False
    for index, character in enumerate(text):
        if quote == '"':
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if quote == "'":
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "#":
            return None
        elif character == "=":
            return text[index + 1 :]
    return None


def _find_multiline_opening(text: str) -> tuple[str, int] | None:
    """Find a multiline-string opener outside comments/single-line strings."""

    index = 0
    while index < len(text):
        if text.startswith('"""', index):
            return '"""', index
        if text.startswith("'''", index):
            return "'''", index
        character = text[index]
        if character == "#":
            return None
        if character == '"':
            index += 1
            escaped = False
            while index < len(text):
                character = text[index]
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    index += 1
                    break
                index += 1
            continue
        if character == "'":
            closing = text.find("'", index + 1)
            if closing < 0:
                return None
            index = closing + 1
            continue
        index += 1
    return None


def _find_multiline_close(text: str, delimiter: str, start: int) -> int:
    index = text.find(delimiter, start)
    while index >= 0 and delimiter == '"""':
        backslashes = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            break
        index = text.find(delimiter, index + 1)
    return index


def _multiline_state_after_line(
    text: str, active: str | None = None
) -> str | None:
    """Track only whether a valid unrelated TOML multiline string continues."""

    remaining = text
    delimiter = active
    while True:
        if delimiter is None:
            opening = _find_multiline_opening(remaining)
            if opening is None:
                return None
            delimiter, start = opening
            close = _find_multiline_close(remaining, delimiter, start + 3)
        else:
            close = _find_multiline_close(remaining, delimiter, 0)
        if close < 0:
            return delimiter
        remaining = remaining[close + 3 :]
        delimiter = None


def _parse_codex_plugins_compat(config_text: str) -> Mapping[str, Mapping[str, bool]]:
    """Parse the exact Codex plugin-table subset when stdlib TOML is absent.

    Supported plugin state is deliberately limited to
    ``[plugins."identity"]`` followed by at most one boolean ``enabled`` key.
    Any other syntax that targets the ``plugins`` namespace fails closed.
    Unrelated TOML sections and assignments are outside this compatibility
    parser's responsibility and are ignored.
    """

    plugins: dict[str, dict[str, bool]] = {}
    current_identity: str | None = None
    multiline: str | None = None
    for line_number, raw_line in enumerate(config_text.splitlines(), start=1):
        if multiline is not None:
            multiline = _multiline_state_after_line(raw_line, multiline)
            continue
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            table = _TABLE_HEADER.fullmatch(line)
            array_table = _ARRAY_TABLE_HEADER.fullmatch(line)
            match = table or array_table
            if match is None:
                raise ValueError(f"unsupported TOML table at line {line_number}")
            body = match.group("body").strip()
            root = _first_toml_key_segment(body)
            if root != "plugins":
                current_identity = None
                continue
            plugin_table = _PLUGIN_TABLE.fullmatch(body)
            if array_table is not None or plugin_table is None:
                raise ValueError(
                    f"unsupported plugins table at line {line_number}"
                )
            identity = plugin_table.group("identity")
            if identity in plugins:
                raise ValueError(f"duplicate plugins table at line {line_number}")
            plugins[identity] = {}
            current_identity = identity
            continue
        if current_identity is not None:
            enabled = _PLUGIN_ENABLED.fullmatch(line)
            if enabled is None or "enabled" in plugins[current_identity]:
                raise ValueError(
                    f"unsupported plugins entry at line {line_number}"
                )
            plugins[current_identity]["enabled"] = enabled.group("value") == "true"
            continue
        try:
            root = _first_toml_key_segment(line)
        except ValueError:
            continue
        if root == "plugins":
            raise ValueError(
                f"unsupported plugins assignment at line {line_number}"
            )
        rhs = _assignment_rhs(line)
        if rhs is not None:
            multiline = _multiline_state_after_line(rhs)
    if multiline is not None:
        raise ValueError("unterminated TOML multiline string")
    return plugins


def _load_policy():
    path = PLUGIN_ROOT / "host_policy.py"
    spec = importlib.util.spec_from_file_location("agent_collab_doctor_policy", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_runtime_client():
    path = PLUGIN_ROOT / "runtime_client.py"
    spec = importlib.util.spec_from_file_location("agent_collab_doctor_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class LegacyObservation:
    package: str
    host_runtime: str
    state: str
    evidence: str


@dataclass(frozen=True)
class LegacyInventory:
    active_packages: tuple[str, ...]
    installed_packages: tuple[str, ...]
    cached_packages: tuple[str, ...]
    evidence: tuple[str, ...]
    observations: tuple[LegacyObservation, ...]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class DoctorReport:
    active_legacy_packages: tuple[str, ...]
    installed_legacy_packages: tuple[str, ...]
    cached_legacy_packages: tuple[str, ...]
    legacy_observations: tuple[Mapping[str, str], ...]
    inventory_errors: tuple[str, ...]
    host_profile: Mapping[str, object]
    native_runtime: str
    broker_runtime: str
    provider_routing: str
    actions: tuple[str, ...]


def inventory_legacy_packages(home: Path) -> LegacyInventory:
    try:
        home = home.expanduser().resolve()
    except (OSError, RuntimeError, KeyError) as exc:
        return LegacyInventory(
            (),
            (),
            (),
            (),
            (),
            (f"cannot resolve home directory: {type(exc).__name__}",),
        )
    active: set[str] = set()
    installed: set[str] = set()
    cached: set[str] = set()
    evidence: list[str] = []
    errors: list[str] = []
    observations: set[LegacyObservation] = set()

    def observe(package: str, host: str, state: str, source: str) -> None:
        evidence.append(source)
        observations.add(LegacyObservation(package, host, state, source))

    def read_registry(path: Path) -> str | None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            errors.append(f"inventory registry is unreadable: {path}: {type(exc).__name__}")
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            errors.append(f"inventory registry is unsafe: {path}")
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"inventory registry is unreadable: {path}: {type(exc).__name__}")
            return None

    active_roots = (
        (home / ".claude" / "plugins", "claude-code"),
        (home / ".codex" / "plugins", "codex"),
        (home / ".gemini" / "config" / "plugins", "antigravity"),
    )
    for package in LEGACY_PACKAGES:
        for root, host in active_roots:
            candidate = root / package
            if candidate.exists() or candidate.is_symlink():
                active.add(package)
                installed.add(package)
                observe(package, host, "filesystem-active", str(candidate))
        for cache_root in (
            home / ".claude" / "plugins" / "cache",
            home / ".codex" / "plugins" / "cache",
        ):
            if cache_root.is_dir():
                matches = list(cache_root.glob(f"**/{package}"))
                if matches:
                    cached.add(package)
                    evidence.extend(str(path) for path in matches)
    for registry, host, kind in (
        (home / ".claude" / "settings.json", "claude-code", "settings"),
        (
            home / ".claude" / "plugins" / "installed_plugins.json",
            "claude-code",
            "installed",
        ),
        (home / ".codex" / "settings.json", "codex", "settings"),
    ):
        raw_registry = read_registry(registry)
        if raw_registry is None:
            continue
        try:
            document = json.loads(raw_registry)
        except (ValueError, RecursionError):
            errors.append(f"inventory registry is malformed: {registry}")
            continue
        if not isinstance(document, Mapping):
            errors.append(f"inventory registry has invalid root shape: {registry}")
            continue
        field = "enabledPlugins" if kind == "settings" else "plugins"
        if field not in document:
            if kind == "installed":
                errors.append(f"inventory registry is missing {field}: {registry}")
            continue
        selections = document[field]
        if not isinstance(selections, Mapping):
            errors.append(f"inventory registry has invalid {field} shape: {registry}")
            continue
        for identity, selection in selections.items():
            package = str(identity).split("@", 1)[0]
            if package not in LEGACY_PACKAGES:
                continue
            installed.add(package)
            if kind == "installed":
                state = "registry-installed"
            elif selection is True:
                active.add(package)
                state = "registry-enabled"
            elif selection is False:
                state = "registry-selected-disabled"
            else:
                state = "registry-selected-unknown"
            observe(package, host, state, f"{registry}:{field}.{identity}")

    codex_config = home / ".codex" / "config.toml"
    config_text = read_registry(codex_config)
    codex_plugins: Mapping[str, object] = {}
    if config_text is not None:
        try:
            if tomllib is None:
                codex_plugins = _parse_codex_plugins_compat(config_text)
            else:
                parsed = tomllib.loads(config_text)
                candidate = (
                    parsed.get("plugins", {}) if isinstance(parsed, Mapping) else None
                )
                if isinstance(candidate, Mapping):
                    codex_plugins = candidate
                else:
                    errors.append(
                        f"inventory registry has invalid plugins shape: {codex_config}"
                    )
        except (ValueError, TypeError, RecursionError):
            errors.append(f"inventory registry is malformed: {codex_config}")
    for identity, settings in codex_plugins.items():
        package = str(identity).split("@", 1)[0]
        if package not in LEGACY_PACKAGES:
            continue
        installed.add(package)
        enabled = settings.get("enabled") if isinstance(settings, Mapping) else None
        if enabled is True:
            active.add(package)
            state = "enabled"
        elif enabled is False:
            state = "installed-disabled"
        else:
            state = "installed-unknown"
        observe(
            package,
            "codex",
            state,
            f"{codex_config}:plugins.{identity}",
        )
    return LegacyInventory(
        tuple(sorted(active)),
        tuple(sorted(installed)),
        tuple(sorted(cached)),
        tuple(sorted(set(evidence))),
        tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.host_runtime,
                    item.package,
                    item.state,
                    item.evidence,
                ),
            )
        ),
        tuple(sorted(set(errors))),
    )


def _runtime_state() -> str:
    client = _load_runtime_client()
    resolution = client.resolve_runtime()
    if resolution.status == client.RuntimeStatus.OK:
        missing = set(client.SUPPORTED_CONTRACTS).difference(resolution.contracts)
        if missing:
            rendered = ",".join(f"{route}/{action}" for route, action in sorted(missing))
            return "invalid: missing contracts " + rendered
        return "available"
    if resolution.status == client.RuntimeStatus.UNAVAILABLE:
        return "typed unavailable"
    return f"invalid: {resolution.status.value}"


def _broker_runtime_state() -> str:
    client = _load_runtime_client()
    status = client.broker_status()
    if status.status == client.RuntimeStatus.OK:
        return "ready"
    if status.status == client.RuntimeStatus.UNAVAILABLE:
        return "unavailable"
    if status.status == client.RuntimeStatus.INTEGRITY_ERROR:
        return "integrity_error"
    return "unproven"


def build_report(
    *, home: Path, explicit_config: Mapping[str, str] | None
) -> DoctorReport:
    inventory = inventory_legacy_packages(home)
    policy = _load_policy()
    profile = policy.resolve_profile(explicit_config)
    runtime = _runtime_state()
    broker_runtime = _broker_runtime_state()
    blocked = bool(
        inventory.active_packages or inventory.installed_packages or inventory.errors
    )
    host = profile.host_runtime
    if host == "claude-code":
        actions = [
            "INSTALL: /plugin install agent-collab@agent-collab",
            "VERIFY: /agent-collab:migration-doctor",
        ]
    elif host == "codex":
        actions = [
            "INSTALL: codex plugin add agent-collab@agent-collab",
            "VERIFY: run the agent-collab migration-doctor skill",
        ]
    elif host == "antigravity":
        actions = [
            "MANUAL: select only agent-collab in the Antigravity plugin manager",
            "VERIFY: run the agent-collab migration-doctor skill",
        ]
    elif host == "opencode":
        actions = [
            "MANUAL: select only agent-collab in the ZCode/OpenCode plugin manager",
            "VERIFY: run the agent-collab migration-doctor skill",
        ]
    else:
        actions = [
            "MANUAL: install/select only the agent-collab package in this host runtime",
            "VERIFY: invoke plugin-relative migration_doctor.py",
        ]
    removal_targets = {
        (item.package, item.host_runtime) for item in inventory.observations
    }
    for package in inventory.installed_packages:
        if not any(candidate == package for candidate, _ in removal_targets):
            removal_targets.add((package, host))
    for package, observed_host in sorted(removal_targets):
        if observed_host == "claude-code":
            actions.append(
                f"UNINSTALL: claude plugin uninstall -s user -y {package}@agent-collab"
            )
        elif observed_host == "codex":
            actions.append(
                f"UNINSTALL: codex plugin remove {package}@agent-collab --json"
            )
        else:
            actions.append(
                f"MANUAL: remove {package}@agent-collab from the active "
                f"{observed_host} plugin selection"
            )
    routing_ready = (
        not blocked and runtime == "available" and broker_runtime == "ready"
    )
    return DoctorReport(
        active_legacy_packages=inventory.active_packages,
        installed_legacy_packages=inventory.installed_packages,
        cached_legacy_packages=inventory.cached_packages,
        legacy_observations=tuple(asdict(item) for item in inventory.observations),
        inventory_errors=inventory.errors,
        host_profile=asdict(profile),
        native_runtime=runtime,
        broker_runtime=broker_runtime,
        provider_routing="READY" if routing_ready else "BLOCKED",
        actions=tuple(actions),
    )


def render_report(report: DoctorReport) -> str:
    lines = [
        f"PROVIDER ROUTING: {report.provider_routing}",
        "ACTIVE LEGACY: " + (", ".join(report.active_legacy_packages) or "none"),
        "INSTALLED LEGACY: "
        + (", ".join(report.installed_legacy_packages) or "none"),
        "CACHED LEGACY: " + (", ".join(report.cached_legacy_packages) or "none"),
        *(
            "LEGACY OBSERVATION: "
            f"{item['host_runtime']} / {item['state']} / {item['package']} / "
            f"{item['evidence']}"
            for item in report.legacy_observations
        ),
        *(f"INVENTORY ERROR: {error}" for error in report.inventory_errors),
        f"HOST PROFILE: {report.host_profile['primary_id']} / {report.host_profile['primary_family']}",
        f"NATIVE RUNTIME: {report.native_runtime}",
        f"BROKER RUNTIME: {report.broker_runtime}",
        *report.actions,
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        home=args.home if args.home is not None else Path("~"),
        explicit_config=None,
    )
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_report(report))
    return 1 if report.provider_routing == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
