"""Provider-free environment projection tests for the public runtime client."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "plugins" / "agent-collab" / "runtime_client.py"


def _load_client():
    spec = importlib.util.spec_from_file_location("runtime_client_configuration", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeClientConfigurationEnvironmentTests(unittest.TestCase):
    def test_preserves_native_login_and_catalog_locations_without_credentials(self) -> None:
        client = _load_client()
        configured = {
            "CODEX_HOME": "/operator/codex",
            "GEMINI_HOME": "/operator/gemini",
            "CLAUDE_CONFIG_DIR": "/operator/claude",
            "GROK_HOME": "/operator/grok",
            "GROK_AUTH_PATH": "/operator/grok/auth.json",
            "OPENCODE_HOME": "/operator/opencode",
            "XDG_CONFIG_HOME": "/operator/xdg-config",
            "XDG_DATA_HOME": "/operator/xdg-data",
            "XDG_CACHE_HOME": "/operator/xdg-cache",
            "XDG_STATE_HOME": "/operator/xdg-state",
            "EXAMPLE_API_KEY": "not-forwarded",
            "OPENCODE_CONFIG_CONTENT": "not-forwarded",
        }
        with tempfile.TemporaryDirectory() as raw, mock.patch.dict(
            os.environ, configured, clear=True
        ):
            environment = client._scrubbed_env(Path(raw))

        for name, value in configured.items():
            if name in {"EXAMPLE_API_KEY", "OPENCODE_CONFIG_CONTENT"}:
                self.assertNotIn(name, environment)
            else:
                self.assertEqual(environment[name], value)
