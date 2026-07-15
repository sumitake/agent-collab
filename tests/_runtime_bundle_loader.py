"""Load the public runtime-bundle verifier without making the plugin a package."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE = Path(__file__).resolve().parents[1] / "plugins" / "agent-collab" / "runtime_bundle.py"
spec = importlib.util.spec_from_file_location("agent_collab_public_runtime_bundle", MODULE)
if spec is None or spec.loader is None:
    raise RuntimeError("public runtime bundle verifier cannot be loaded")
rb = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rb
spec.loader.exec_module(rb)
