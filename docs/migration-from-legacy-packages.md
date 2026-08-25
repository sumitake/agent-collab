# Migrating from retired collaboration packages

Install or select only `agent-collab`. Retired provider-branded packages are
not compatibility dependencies and must not remain active.

## Skill changes

- Replace provider-branded review, architecture, governance, and codegen skill
  names with the matching `agent-collab` semantic skill.
- Replace every `long-context` or size-branded context command with
  `/agent-collab:context`.
- `/agent-collab:ai-merge-resolve`, `/claude-collab:ai-merge-resolve`, `/codex-collab:ai-merge-resolve`, `/antigravity-collab:ai-merge-resolve` | `/agent-collab:merge-resolve`
- Send a logical action and source to the coordinator. Exact `action` and
  `route` field names are accepted only when their values already name a public
  logical action and canonical logical agent. Old provider route/action pairs,
  models, transport actions, and product aliases remain unsupported; that wire
  has been removed.

## Verify

Run:

```text
python3 "<plugin-root>/migration_doctor.py" --json
```

The provider-free report distinguishes active, installed, and cached legacy
observations. Active retired packages block direct routing. Cache-only residue
does not become an executable route.

The current package unit is manifest schema 4, runtime protocol 4, native
contract 4, provider runtime `4.2.1`, and descriptor schema 7. The generated
manifest carries one top-level `wire_contract` and
`wire_contract_sha256`. A mixed unit fails typed.

No broker, socket, plist, selector, lane, launchd job, installed runtime copy,
or setup lifecycle is required. Do not restore a retired provider package as a
rollback path.
