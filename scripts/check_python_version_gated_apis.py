#!/usr/bin/env python3
"""Flag stdlib/language APIs newer than this repo's declared minimum Python version.

Incident this guards against
-----------------------------
A worker-tier model (Grok Composer) generated a unittest-style test file that
called ``self.enterContext(...)`` -- a ``unittest.TestCase`` method added only
in Python 3.11. The primary agent that reviewed and pushed the change ran the
suite locally on a newer interpreter (Python 3.14), where the call resolved
fine, and CI subsequently failed on this repo's Python 3.10 leg with::

    AttributeError: '<TestCase>' object has no attribute 'enterContext'

Root cause: a stdlib/language feature that post-dates the project's declared
minimum Python version is invisible to a local run on a newer interpreter --
a green local run proves nothing about the floor version. Documented in the
sibling ``agent-collab-workspace`` repo's shared learning ledger as entry
``LRN-20260722-074753-claude-6000``
(pattern_key: ``worker.unittest.uses.version.gated.stdlib.api``); this script
is the "prevention" half of that entry's recommendation, installed in the
repo where the incident actually happened (this one -- the failure was in
this plugin repo's test suite, not the workspace repo's).

What this checks
-----------------
Walks the repository's tracked (and untracked-but-not-gitignored) ``*.py``
files and flags known Python stdlib/language APIs that were introduced after
this repo's DECLARED minimum supported Python version, read from the
``python:`` test matrix in ``.github/workflows/ci.yml`` (see
``_read_declared_minimum()``). An API introduced at-or-before the declared
floor is never flagged, even though it's present in the ``KNOWN_APIS`` table
below -- the table intentionally includes a couple of APIs that predate this
repo's current floor (e.g. ``str.removeprefix``/``removesuffix``, 3.9+) so
that lowering the floor in the future is a one-line change to
``FALLBACK_MIN_VERSION`` / ``ci.yml``, not a rewrite of this script.

Detection is AST-based where practical (precise: exact line/col, immune to
false positives from comments or string literals) with a narrow, documented
regex fallback for source that fails to parse under the running interpreter.
The most likely case for that fallback is a file using ``except*`` syntax:
that is a ``SyntaxError`` on Python < 3.11 even though the rest of the file
is otherwise valid, so a checker itself invoked under an old interpreter
cannot even parse the file it's trying to flag.

Usage
-----
    python3 scripts/check_python_version_gated_apis.py              # scan repo
    python3 scripts/check_python_version_gated_apis.py --paths a.py b.py
    python3 scripts/check_python_version_gated_apis.py --min-version 3.11

Exit status: 0 if no gated-API usage is found above the floor, 1 otherwise.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Fallback floor used only if the CI workflow's python matrix can't be found
# or parsed (e.g. this script is copied into a repo without that file, or is
# pointed at a stripped-down checkout). Keep this in sync by hand with the
# lowest version actually listed in ci.yml's `python:` matrix -- but treat
# `_read_declared_minimum()` as the source of truth whenever ci.yml is
# present and parses cleanly; a regression test asserts the two agree
# against the real repo file, so drift here is caught in CI rather than
# discovered the hard way.
FALLBACK_MIN_VERSION: tuple[int, int] = (3, 10)

EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    col: int
    api: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: [{self.api}] {self.message}"


@dataclass(frozen=True)
class GatedAPI:
    """One stdlib/language feature tied to the Python version that introduced it."""

    key: str
    introduced: tuple[int, int]
    message: str
    # Each detector receives the parsed AST (or None if the source failed to
    # parse under the running interpreter) plus the raw source text, and
    # yields (line, col) tuples for every usage site it finds.
    detector: Callable[["ast.Module | None", str], Iterator[tuple[int, int]]]


def _version_str(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------


def _detect_enter_context(tree: "ast.Module | None", source: str) -> Iterator[tuple[int, int]]:
    """``self.enterContext(...)`` calls specifically.

    ``unittest.TestCase.enterContext`` was added in Python 3.11
    (https://docs.python.org/3/library/unittest.html#unittest.TestCase.enterContext).
    We can't cheaply prove the receiver is actually a ``TestCase`` without
    type inference, so this narrows to the receiver being the bare name
    ``self`` -- the only realistic call shape for a ``TestCase`` instance
    method invoked from within a test method (and the exact shape of the
    incident this check guards against: "replaced all 92 self.enterContext(cm)
    call sites", per LRN-20260722-074753-claude-6000).

    Deliberately does NOT flag ``<other-name>.enterContext(...)`` (e.g.
    ``stack.enterContext(...)``, ``ExitStack().enterContext(...)``, or
    ``self.stack.enterContext(...)`` where the immediate receiver is the
    Attribute ``self.stack``, not the bare Name ``self``): ``contextlib.
    ExitStack.enterContext`` has existed since Python 3.3 and is a standard,
    fully 3.10-compatible pattern -- flagging it by name alone (the original
    implementation's approach) would false-positive on legitimate code every
    bit as often as it catches the real incident, defeating the purpose of a
    precision-over-recall guard for a specific known API. A test method that
    genuinely assigns ``self.enterContext = SomeCallable`` or otherwise
    shadows the real method is out of scope -- vanishingly unlikely and not
    worth the added complexity.
    """
    if tree is None:
        for lineno, line in enumerate(source.splitlines(), start=1):
            match = re.search(r"\bself\.enterContext\s*\(", line)
            if match:
                yield lineno, match.start() + 1
        return
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "enterContext"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            yield node.lineno, node.col_offset


_EXCEPT_STAR_RE = re.compile(r"^(\s*)except\s*\*")


def _detect_except_star(tree: "ast.Module | None", source: str) -> Iterator[tuple[int, int]]:
    r"""``except*`` exception-group syntax (PEP 654, Python 3.11+).

    AST-based when the running interpreter's ``ast`` module models it
    (``ast.TryStar``, itself only present on Python 3.11+): this gives exact
    line/col and can't be confused by e.g. an ``except (A, B):`` clause or a
    stray ``*`` elsewhere in the file. Falls back to a line-anchored regex
    (``^\s*except\s*\*``) when the source failed to parse under the running
    interpreter -- most notably, this checker being run on Python 3.10 or
    older cannot parse ``except*`` AT ALL, so a genuine ``SyntaxError`` is
    the *expected* signal there, not a bug to route around.

    Regex-fallback limitation (documented, not silently accepted): this only
    looks at the literal text of each line, so it cannot distinguish a real
    ``except*`` clause from one that happens to appear inside a string or
    comment at the start of a line. In practice an ``except*`` prefix
    embedded in a string/comment at column 0 (ignoring leading whitespace)
    is vanishingly unlikely in real code; if this ever produces a false
    positive, tighten the pattern or special-case the file rather than
    dropping the fallback path entirely -- the alternative is silently
    missing real ``except*`` usage on exactly the interpreter version this
    check exists to protect.
    """
    if tree is not None and hasattr(ast, "TryStar"):
        for node in ast.walk(tree):
            if isinstance(node, ast.TryStar):
                yield node.lineno, node.col_offset
        return
    for lineno, line in enumerate(source.splitlines(), start=1):
        match = _EXCEPT_STAR_RE.match(line)
        if match:
            yield lineno, len(match.group(1))


# A MISSING MODULE (`import tomllib` on 3.10) raises ModuleNotFoundError,
# which IS an ImportError subclass -- so `except ModuleNotFoundError:`,
# `except ImportError:`, or either broad ancestor all genuinely catch it.
_MISSING_MODULE_GUARD_EXCEPTION_NAMES = {
    "ImportError",
    "ModuleNotFoundError",
    "Exception",
    "BaseException",
}

# A MISSING NAME from an EXISTING module (`from typing import Self` on 3.10 --
# `typing` imports fine, it just has no `Self`) raises a PLAIN ImportError,
# NOT ModuleNotFoundError. Since ModuleNotFoundError is a strict SUBCLASS of
# ImportError, `except ModuleNotFoundError:` is NARROWER and never fires for
# this case -- so it must NOT be accepted as a guard here, or a genuinely
# unprotected `from typing import Self` reads as safely guarded and the
# finding is silently suppressed (the exact false negative this split fixes).
_MISSING_NAME_GUARD_EXCEPTION_NAMES = {
    "ImportError",
    "Exception",
    "BaseException",
}


def _handler_catches_import_error(
    handler: ast.ExceptHandler,
    guard_names: "set[str]" = None,  # noqa: RUF013 -- default resolved below
) -> bool:
    """True if this handler's declared exception TYPE(s) would receive the
    relevant import failure at runtime -- a bare ``except:``, or a handler
    naming any exception in `guard_names`. A narrower or unrelated type
    (e.g. ``except ValueError:``) does NOT match.

    `guard_names` selects WHICH exception set counts, because the two import
    failure modes raise DIFFERENT exceptions and therefore accept different
    guards (see the two module-level sets above): a missing MODULE raises
    ModuleNotFoundError, but a missing NAME from an existing module raises a
    plain ImportError that `except ModuleNotFoundError:` cannot catch.
    Defaults to the missing-module set for backwards compatibility.

    Pure type-matching only -- does NOT consider whether the handler
    actually suppresses (vs. re-raises); see `_handler_reraises_unconditionally`
    for that, and `_first_import_matching_handler` for how the two combine
    with Python's actual handler-PRECEDENCE semantics (first-match-wins).
    """
    if guard_names is None:
        guard_names = _MISSING_MODULE_GUARD_EXCEPTION_NAMES
    if handler.type is None:
        return True
    names: list[str] = []
    if isinstance(handler.type, ast.Name):
        names = [handler.type.id]
    elif isinstance(handler.type, ast.Tuple):
        names = [elt.id for elt in handler.type.elts if isinstance(elt, ast.Name)]
    return any(name in guard_names for name in names)


def _first_import_matching_handler(
    handlers: "list[ast.ExceptHandler]",
    guard_names: "set[str]" = None,  # noqa: RUF013 -- default resolved in callee
) -> "ast.ExceptHandler | None":
    """Return the FIRST handler (declaration order) that would actually
    RECEIVE an ImportError/ModuleNotFoundError at runtime, per Python's own
    handler-matching semantics: handlers are tried in order and the first
    one whose type matches wins -- any LATER handler for an
    already-matched exception type is unreachable dead code.

    This matters because a naive "does ANY handler in this try/except look
    like a guard" check (this function's predecessor) would wrongly treat
    e.g. ``except Exception: raise`` followed by
    ``except ImportError: tomllib = None`` as guarded: the broad
    ``Exception`` handler catches the ImportError FIRST and re-raises: the
    later, syntactically-present ``except ImportError:`` fallback is never
    actually reached. Only the FIRST matching handler's suppress-or-not
    status is what determines whether the import is truly guarded.

    Returns None if no handler in the list would catch an ImportError-family
    exception at all.
    """
    for handler in handlers:
        if _handler_catches_import_error(handler, guard_names):
            return handler
    return None


def _handler_reraises_unconditionally(handler: ast.ExceptHandler) -> bool:
    """True if ANY top-level statement in `handler`'s body is a `raise` --
    a bare `raise` (re-raising the currently-handled exception) OR `raise
    SomeOtherError(...)` (raising a NEW exception). Neither provides an
    actual fallback for the gated import: the import still fails, just
    with a possibly different exception type than the original
    ImportError/ModuleNotFoundError.

    Deliberately ANY top-level statement, not just the LAST one (round-3
    finding, managed grok/governance): checking only `body[-1]` misses
    unconditional dead code after an earlier raise, e.g.
    `except ImportError:\\n    raise\\n    tomllib = None` -- the
    `tomllib = None` assignment is genuinely unreachable (the `raise`
    above it always exits first), so the handler still provides NO real
    fallback despite its last statement not being the `raise` itself.
    Fail-closed is the right bias for a CI compatibility gate: this is
    STILL top-level-only (a `raise` nested inside an `if`/`else` branch is
    not detected -- that would require real control-flow analysis to know
    whether every path re-raises), but within that scope, ANY top-level
    `raise` anywhere disqualifies the handler as a guard, not only a
    trailing one.
    """
    if not handler.body:
        return False
    return any(isinstance(stmt, ast.Raise) for stmt in handler.body)


def _guarded_import_lines(
    tree: ast.Module,
    guard_names: "set[str]" = None,  # noqa: RUF013 -- default resolved below
) -> set[int]:
    """Line numbers inside a ``try:`` body whose ``except`` guards import errors.

    Used to suppress the ``tomllib`` / ``typing.Self`` import detectors for
    statements already wrapped in the standard optional-import idiom, so this
    checker doesn't cry wolf on the exact pattern it wants developers to use.

    `guard_names` selects which exception names count as a real guard, and
    MUST match the failure mode the calling detector is about (defaults to
    the missing-MODULE set): `import tomllib` failing raises
    ModuleNotFoundError, but `from typing import Self` failing raises a
    PLAIN ImportError -- so `except ModuleNotFoundError:` guards the former
    and NOT the latter. Passing the wrong set silently suppresses a real
    finding; see the two `_*_GUARD_EXCEPTION_NAMES` sets for the details.

    Deliberately does NOT descend into nested function/async-function bodies
    when collecting protected lines: an import statement textually inside a
    guarded `try:` block but INSIDE A NESTED `def`/`async def` does not
    actually execute at `try`-time -- it executes later, whenever that
    function is called, entirely outside the try/except's protection (e.g.
    `try:\\n    def load():\\n        import tomllib\\n except ImportError:
    \\n    pass` -- the `import tomllib` only ever runs when `load()` is
    called, by which point the enclosing try/except has already finished and
    provides no protection). Marking it "guarded" would be a false negative
    that lets an unguarded, still-broken-on-3.10 import through unflagged.

    Only matches `ast.Try`, NOT `ast.TryStar` (PEP 654 `try: ... except*
    X:` exception groups) -- intentional, not an oversight: an import
    guarded only via `except*` is NOT recognized as protected here, but
    this is fail-closed (an extra, redundant finding), never a silent
    miss. `except*` itself is a separate 3.11+ gated API with its own
    detector (`_detect_except_star`), so a file relying on it to guard an
    import already gets flagged for the `except*` usage regardless of
    whether the guarded import is *also* (redundantly) flagged -- there is
    no path where this combination slips past the checker entirely
    unflagged. Verified via managed grok/governance review before this
    module's checked-in state.

    KNOWN LIMITATION -- nested handlers that CONVERT the exception type.
    An import inside a nested try whose inner handler converts the failure
    (`except ImportError: raise RuntimeError(...)`), wrapped by an outer
    try whose handler catches only the ORIGINAL type, is currently treated
    as guarded even though the outer handler cannot catch the converted
    RuntimeError and the import genuinely still fails. Correctly modeling
    this requires tracking which exception type actually ESCAPES each
    nested try -- i.e. real exception-flow analysis, materially beyond the
    per-handler, top-level-statement heuristics this module is built on.
    Recorded as a known false negative rather than patched: this detector
    accumulated six consecutive rounds of semantic corrections during
    review, and the right next step for this class of gap is a deliberate
    redesign of the guard model, not a seventh incremental heuristic. See
    the PR discussion on #75/#76 for the full history.
    """
    if guard_names is None:
        guard_names = _MISSING_MODULE_GUARD_EXCEPTION_NAMES
    guarded: set[int] = set()

    def _walk_without_nested_functions(node: ast.AST):
        # Check the STARTING node itself, not just children encountered
        # during recursion -- a top-level `try:` body statement can BE a
        # FunctionDef directly (e.g. `try:\n    def load(): ...`), and that
        # case must also be excluded, not just a FunctionDef found nested
        # deeper inside some other statement.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from _walk_without_nested_functions(child)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        matching = _first_import_matching_handler(node.handlers, guard_names)
        if matching is None or _handler_reraises_unconditionally(matching):
            # No handler catches an ImportError-family exception at all, OR
            # the FIRST one that does re-raises without suppressing --
            # either way, this try/except provides no real protection.
            continue
        for stmt in node.body:
            for sub in _walk_without_nested_functions(stmt):
                lineno = getattr(sub, "lineno", None)
                if lineno is not None:
                    guarded.add(lineno)
    return guarded


def _detect_tomllib_import(tree: "ast.Module | None", source: str) -> Iterator[tuple[int, int]]:
    """``import tomllib`` / ``from tomllib import ...`` (stdlib module added in 3.11).

    Regex-fallback limitation: an unparseable file's regex scan below cannot
    tell whether the import is wrapped in a ``try/except ImportError`` guard
    (the AST path can, and does -- see ``_guarded_import_lines``), so it may
    flag an already-safe guarded import that the AST path would correctly
    ignore. This is a documented precision trade-off specific to files the
    running interpreter can't parse at all.
    """
    if tree is None:
        for lineno, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("import tomllib") or stripped.startswith(
                "from tomllib import"
            ):
                yield lineno, len(line) - len(line.lstrip())
        return
    guarded = _guarded_import_lines(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if node.lineno in guarded:
                continue
            for alias in node.names:
                if alias.name == "tomllib" or alias.name.startswith("tomllib."):
                    yield node.lineno, node.col_offset
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "tomllib" or node.module.startswith("tomllib."))
            and node.lineno not in guarded
        ):
            yield node.lineno, node.col_offset


def _detect_typing_self(tree: "ast.Module | None", source: str) -> Iterator[tuple[int, int]]:
    """``typing.Self`` / ``from typing import Self`` (PEP 673, added in Python 3.11).

    The ``from typing import Self`` import form is suppressed inside a
    ``try/except ImportError``-style guard, same as the ``tomllib`` detector
    above (see ``_guarded_import_lines``). The ``typing.Self`` attribute-usage
    form (e.g. in a type annotation) is flagged unconditionally regardless of
    surrounding try/except -- it's materially harder to guard meaningfully
    (annotations frequently aren't evaluated at runtime at all under
    ``from __future__ import annotations``, so a runtime guard wouldn't even
    fire), and unguarded is the common case in practice.
    """
    if tree is None:
        for lineno, line in enumerate(source.splitlines(), start=1):
            if re.search(r"\bfrom\s+typing\s+import\b.*\bSelf\b", line) or re.search(
                r"\btyping\.Self\b", line
            ):
                yield lineno, len(line) - len(line.lstrip())
        return
    # MISSING-NAME guard set, not the missing-module default: on 3.10,
    # `from typing import Self` fails with a PLAIN ImportError (the `typing`
    # module imports fine, it simply has no `Self`), so a narrower
    # `except ModuleNotFoundError:` never fires and must NOT count as a
    # guard here -- accepting it would silently suppress a real finding.
    guarded = _guarded_import_lines(tree, _MISSING_NAME_GUARD_EXCEPTION_NAMES)
    # Resolve the local name(s) `typing` is bound to in this module, so the
    # common alias form `import typing as t` + `t.Self` is detected too --
    # a name-only `typing.Self` check misses it entirely, which would be a
    # silent miss of exactly the API this detector exists to catch (on
    # Python 3.10 without postponed annotation evaluation, defining such an
    # annotation raises AttributeError at definition time).
    typing_aliases = {"typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "typing":
                    typing_aliases.add(alias.asname or "typing")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "typing"
            and node.lineno not in guarded
        ):
            for alias in node.names:
                if alias.name == "Self":
                    yield node.lineno, node.col_offset
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "Self"
            and isinstance(node.value, ast.Name)
            and node.value.id in typing_aliases
        ):
            yield node.lineno, node.col_offset


def _detect_method_call(
    tree: "ast.Module | None", source: str, method_name: str
) -> Iterator[tuple[int, int]]:
    """Flag any `<anything>.<method_name>(...)` call by METHOD NAME ALONE.

    Known limitation (currently latent, deliberately not fixed): this
    cannot establish the receiver's TYPE, so if the declared floor is ever
    lowered below 3.9 -- activating the `str.removeprefix`/`removesuffix`
    entries, which are inert at today's 3.10 floor -- a user-defined
    `.removeprefix()` method on some non-str class would also be flagged,
    a blocking CI false positive. Fixing that properly needs receiver type
    inference (or a str-literal/annotation heuristic), which is
    disproportionate while these entries cannot fire at all. If the floor
    is ever lowered below 3.9, tighten this first. Deliberately NOT
    generalized to `enterContext`, whose detector narrows on the receiver
    name (`self`) precisely because that one IS active at the current
    floor.
    """
    if tree is None:
        pattern = re.compile(r"\." + re.escape(method_name) + r"\s*\(")
        for lineno, line in enumerate(source.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                yield lineno, match.start() + 1
        return
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method_name
        ):
            yield node.lineno, node.col_offset


def _detect_str_removeprefix(tree: "ast.Module | None", source: str) -> Iterator[tuple[int, int]]:
    """``str.removeprefix(...)`` (PEP 616, added in Python 3.9)."""
    yield from _detect_method_call(tree, source, "removeprefix")


def _detect_str_removesuffix(tree: "ast.Module | None", source: str) -> Iterator[tuple[int, int]]:
    """``str.removesuffix(...)`` (PEP 616, added in Python 3.9)."""
    yield from _detect_method_call(tree, source, "removesuffix")


# ---------------------------------------------------------------------------
# Known-API table -- grow this list as new version-gated incidents surface.
# Only APIs with `introduced > declared_minimum` are actually flagged; see
# `applicable_apis()`.
# ---------------------------------------------------------------------------

KNOWN_APIS: tuple[GatedAPI, ...] = (
    GatedAPI(
        key="unittest.TestCase.enterContext",
        introduced=(3, 11),
        message=(
            "unittest.TestCase.enterContext() was added in Python 3.11; use "
            "addCleanup(cm.__exit__, ...) or a manual contextlib.ExitStack "
            "for compatibility with the declared floor."
        ),
        detector=_detect_enter_context,
    ),
    GatedAPI(
        key="except*",
        introduced=(3, 11),
        message=(
            "except* exception-group syntax (PEP 654) was added in Python "
            "3.11 and is a SyntaxError on older interpreters."
        ),
        detector=_detect_except_star,
    ),
    GatedAPI(
        key="tomllib",
        introduced=(3, 11),
        message=(
            "the tomllib stdlib module was added in Python 3.11; use the "
            "third-party 'tomli' package (or equivalent) for compatibility "
            "with the declared floor."
        ),
        detector=_detect_tomllib_import,
    ),
    GatedAPI(
        key="typing.Self",
        introduced=(3, 11),
        message=(
            "typing.Self (PEP 673) was added in Python 3.11; use a TypeVar "
            "bound to the class instead for compatibility with the declared "
            "floor."
        ),
        detector=_detect_typing_self,
    ),
    GatedAPI(
        key="str.removeprefix",
        introduced=(3, 9),
        message="str.removeprefix() was added in Python 3.9 (PEP 616).",
        detector=_detect_str_removeprefix,
    ),
    GatedAPI(
        key="str.removesuffix",
        introduced=(3, 9),
        message="str.removesuffix() was added in Python 3.9 (PEP 616).",
        detector=_detect_str_removesuffix,
    ),
)


def applicable_apis(min_version: tuple[int, int]) -> tuple[GatedAPI, ...]:
    """APIs introduced strictly after `min_version` -- i.e. actually gated for it."""
    return tuple(api for api in KNOWN_APIS if api.introduced > min_version)


# ---------------------------------------------------------------------------
# Declared-minimum discovery
# ---------------------------------------------------------------------------

_MATRIX_RE = re.compile(r"python:\s*\[(?P<versions>[^\]]*)\]")
_VERSION_RE = re.compile(r"(\d+)\.(\d+)")


class MinVersionDiscoveryError(Exception):
    """The CI workflow file exists but its Python-version matrix could not
    be parsed in the expected shape -- FORMAT DRIFT, distinct from the file
    simply not existing. Never silently swallow this: a repo where ci.yml
    genuinely exists but no longer parses means this checker's notion of the
    declared floor may be stale, which is exactly the failure mode this
    checker itself exists to prevent for OTHER version-gated assumptions."""


def _parse_declared_minimum(workflow_path: Path) -> tuple[int, int]:
    """Parse the lowest Python version from ci.yml's ``python:`` test matrix.

    This is a narrow, dependency-free regex extraction -- not a YAML parser
    -- matched against the specific ``python: ["3.10", "3.12", "3.14"]``
    shape used in ``.github/workflows/ci.yml`` today. Raises
    ``MinVersionDiscoveryError`` if the file exists but doesn't match that
    shape (multi-line matrix, YAML anchors, a renamed matrix key, an empty
    version list, ...) -- callers must not treat that as equivalent to "no
    workflow file" (see ``_read_declared_minimum``, which is the fail-soft
    wrapper for that genuinely benign case only).
    """
    raw_text = workflow_path.read_text(encoding="utf-8")
    # Strip YAML comments BEFORE matching. Without this, a commented-out
    # stale declaration (`# python: ["3.12"]`) sitting above the ACTIVE
    # matrix wins the unrestricted `search`, and the checker adopts a
    # WRONG, HIGHER floor -- which silently disables every 3.11 detector
    # (applicable_apis() returns nothing) and lets genuinely incompatible
    # code pass CI. That is a fail-OPEN, the worst failure direction for
    # this gate, so comments must never contribute a candidate floor.
    #
    # Line-oriented and quote-naive by design: a `#` inside a quoted YAML
    # scalar would also be treated as starting a comment. That can only
    # ever DISCARD a candidate match (never invent one), so its failure
    # direction is the safe one -- and it routes to the existing
    # MinVersionDiscoveryError fail-loud path rather than to a wrong floor.
    text = "\n".join(line.split("#", 1)[0] for line in raw_text.splitlines())
    match = _MATRIX_RE.search(text)
    if not match:
        raise MinVersionDiscoveryError(
            f"{workflow_path}: python-version matrix pattern not found "
            "(ci.yml's matrix shape may have changed -- update _MATRIX_RE)"
        )
    versions = [
        (int(vmatch.group(1)), int(vmatch.group(2)))
        for vmatch in _VERSION_RE.finditer(match.group("versions"))
    ]
    if not versions:
        raise MinVersionDiscoveryError(
            f"{workflow_path}: matrix pattern matched but no version "
            "strings were extracted from it (regex/format mismatch)"
        )
    return min(versions)


def _read_declared_minimum(workflow_path: Path = CI_WORKFLOW_PATH) -> tuple[int, int]:
    """Read the lowest Python version in ci.yml's ``python:`` test matrix,
    falling back to ``FALLBACK_MIN_VERSION`` ONLY when the workflow file
    itself is absent (e.g. a stripped checkout that doesn't include
    ``.github/``) -- that is the sole benign case. A workflow file that
    EXISTS but no longer matches the expected matrix shape is FORMAT DRIFT,
    not a benign absence, and must not be silently masked by this fallback:
    see ``MinVersionDiscoveryError`` and ``main()``'s handling of it, which
    fails loud instead of silently scanning against a possibly-stale
    constant. ``test_check_python_version_gated_apis.py`` includes a
    regression test that calls ``_parse_declared_minimum`` directly against
    the real repo file and asserts it does NOT raise -- that is what
    actually proves live discovery still works, as opposed to merely
    observing that a silent fallback happens to equal the same constant.
    """
    try:
        return _parse_declared_minimum(workflow_path)
    except OSError:
        return FALLBACK_MIN_VERSION


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def scan_source(source: str, filename: str, min_version: tuple[int, int]) -> list[Finding]:
    """Scan one file's already-read source text for applicable gated APIs."""
    apis = applicable_apis(min_version)
    if not apis:
        return []
    try:
        tree: "ast.Module | None" = ast.parse(source, filename=filename)
    except SyntaxError:
        tree = None
    findings: list[Finding] = []
    for api in apis:
        for line, col in api.detector(tree, source):
            findings.append(
                Finding(path=filename, line=line, col=col, api=api.key, message=api.message)
            )
    findings.sort(key=lambda f: (f.line, f.col, f.api))
    return findings


class SourceReadError(Exception):
    """A tracked Python file could not be decoded even using its OWN
    declared encoding (PEP 263) -- a genuine read failure, not merely "not
    UTF-8 by default". Callers must fail CLOSED on this (surface it as a
    scan failure), never silently treat the file as clean: a file this
    checker can't read is still fully executable by Python and may contain
    an unguarded gated API this checker would otherwise miss entirely.
    """


def _read_source(path: Path) -> str:
    """Read a Python source file using its own declared encoding.

    `tokenize.open` detects and honors a `# -*- coding: ... -*-` PEP 263
    cookie (or assumes UTF-8 per PEP 3120 when none is present), unlike a
    hardcoded `read_text(encoding="utf-8")`, which raised `UnicodeDecodeError`
    -- and was silently swallowed -- for any legitimately non-UTF-8-declared
    but otherwise valid, tracked, executable source file, letting a gated
    API inside it slip past this checker unflagged.

    `FileNotFoundError` is treated as benign (the file listing and the read
    raced, e.g. a file deleted mid-scan) and re-raised as-is for the caller
    to skip silently -- unlike a genuine decode/encoding-cookie failure on a
    file that DOES exist, which raises `SourceReadError` for the caller to
    fail closed on.
    """
    try:
        with tokenize.open(path) as fh:
            return fh.read()
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError) as exc:
        raise SourceReadError(f"{path}: {exc}") from exc


def scan_file(path: Path, min_version: tuple[int, int]) -> list[Finding]:
    """Raises `SourceReadError` on a genuine read/decode failure (see
    `_read_source`) -- the caller must fail closed, not skip silently.
    Returns `[]` (silently) only when the file vanished between listing and
    reading (`FileNotFoundError`), the sole benign case."""
    try:
        source = _read_source(path)
    except FileNotFoundError:
        return []
    return scan_source(source, str(path), min_version)


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield every tracked-or-untracked-but-not-gitignored ``*.py`` file under `root`."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.py",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        for raw in result.stdout.split(b"\0"):
            if not raw:
                continue
            relative = Path(raw.decode("utf-8", errors="surrogateescape"))
            if any(part in EXCLUDED_DIR_NAMES for part in relative.parts):
                continue
            yield root / relative
        return
    # Not a git checkout (or git unavailable) -- fall back to a plain walk.
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIR_NAMES]
        for name in files:
            if name.endswith(".py"):
                yield Path(current) / name


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to scan (default: this repo).",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        type=Path,
        default=None,
        help="Scan only these specific files instead of the whole repo (mainly for tests).",
    )
    parser.add_argument(
        "--min-version",
        type=str,
        default=None,
        help='Override the declared minimum, e.g. "3.11" (default: read from ci.yml).',
    )
    args = parser.parse_args(argv)

    if args.min_version:
        major_str, _, minor_str = args.min_version.partition(".")
        min_version = (int(major_str), int(minor_str))
    else:
        try:
            min_version = _parse_declared_minimum(CI_WORKFLOW_PATH)
        except OSError:
            # Genuinely benign: no ci.yml at all (e.g. a stripped checkout).
            min_version = FALLBACK_MIN_VERSION
        except MinVersionDiscoveryError as exc:
            print(
                f"ERROR: {exc}\n"
                "Refusing to silently scan against a possibly-stale fallback "
                f"(Python {_version_str(FALLBACK_MIN_VERSION)}) when the CI "
                "workflow file exists but its version matrix could not be "
                "parsed. Update _MATRIX_RE/_VERSION_RE in this script to "
                "match the new ci.yml shape, or pass --min-version explicitly "
                "to override.",
                file=sys.stderr,
            )
            return 2

    apis = applicable_apis(min_version)
    if not apis:
        print(
            "No known gated APIs post-date the declared minimum "
            f"(Python {_version_str(min_version)}); nothing to check."
        )
        return 0

    files: Iterable[Path] = args.paths if args.paths else iter_python_files(args.root)

    all_findings: list[Finding] = []
    read_errors: list[str] = []
    scanned = 0
    for path in files:
        scanned += 1
        try:
            all_findings.extend(scan_file(path, min_version))
        except SourceReadError as exc:
            # Fail closed: a tracked .py file this checker could not decode
            # (even using its own declared encoding) is still fully
            # executable by Python and may contain an unguarded gated API.
            # Silently skipping it would be exactly how such a file evades
            # this check entirely.
            read_errors.append(str(exc))

    if read_errors:
        print(
            f"ERROR: {len(read_errors)} tracked Python file(s) could not be "
            "read/decoded (even using each file's own declared encoding) "
            "and were NOT scanned -- refusing to silently treat them as "
            "clean:"
        )
        for err in read_errors:
            print("  " + err)
        print(
            "\nFix the file's encoding (or its PEP 263 encoding cookie) so "
            "it can be read, then re-run this check."
        )
        return 1

    if all_findings:
        print(
            f"Found {len(all_findings)} use(s) of Python-version-gated API(s) "
            f"above the declared minimum (Python {_version_str(min_version)}):"
        )
        for finding in all_findings:
            print("  " + finding.format())
        print(
            "\nThese will fail on the repo's Python "
            f"{_version_str(min_version)} CI leg even though they may pass "
            "locally on a newer interpreter. See LRN-20260722-074753-claude-6000 "
            "in the agent-collab-workspace learning ledger for the incident "
            "this check guards against."
        )
        return 1

    print(
        f"OK: scanned {scanned} Python file(s); no gated-API usage found above "
        f"the declared minimum (Python {_version_str(min_version)})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
