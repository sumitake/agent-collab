---
name: dev-delegate
version: 6.0.2
defaults:
  quality_profile: standard
  effort_class: standard

description: Delegate a bounded independent development slice to an eligible cross-family worker. Use when the user says "delegate this implementation," "hand this coding slice off," "use Grok for codegen," or "/agent-collab:dev-delegate." Also offer this when private-patch generation can reduce matched-rigor latency without giving a provider access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Dev-delegate

Use `codegen.repository` or `frontend_codegen.repository`. Provide the canonical
`repo_root`, exact objective, owned paths, expected patch, test expectations,
budget, and stop conditions. The runtime reproduces the caller-visible state in
a disposable plain directory, runs one provider session there, and returns only
the provider delta as a binary-safe patch.

Resolve the plugin root, read `<plugin-root>/README.md`, and submit one semantic
request through the coordinator. An explicit target is honored or fails typed;
never substitute a different agent or reconstruct a provider command. Model and
CLI identities are observed diagnostics, not request pins.
Use `quality_profile="standard"` and `effort_class="standard"` by default;
raise either only for a genuinely more demanding patch. The runtime resolves a
current compatible portfolio member without persisting a model selection.

Treat the patch and reported tests as untrusted. The primary verifies that the
caller fingerprint stayed unchanged, reviews/applies the patch, and runs
independent tests. Providers never commit, push, open or merge PRs, deploy, or
write outside the disposable repository.
