### agent-collab 7.0.9 — runtime 5.0.12

#### Changed
- Worker guidance distinguishes expected task duration from the runtime's
  admitted-progress inactivity lease, shows how to set an explicit bound, and
  keeps cancellation, partial work, cleanup, and provider status separate. It
  clarifies primary-owned validation as the default and permits worker checks
  only with an exact preverified interpreter and focused command.
- Review guidance grounds external API blockers in the exact called method and
  relevant version, and identifies uncertainty when that evidence is missing.
- Runtime 5.0.12 adds bounded optional hints for certain
  native Agy startup failures without changing request status or returned
  content.
- OpenCode 2 compatibility uses plain ACP startup. Availability checks verify
  model catalog and initialization metadata without creating a session or
  sending a prompt; unknown or contradictory lineage remains unavailable.
- Carrier bindings stay the same: Codex app-server, Gemini through native Agy,
  Grok through ACP, OpenCode ACP for Moonshot, Zhipu, Alibaba and DeepSeek, and
  native Claude structured print for document intent only. Wire schema 12,
  12 logical actions and eight logical agents remain unchanged. No legacy
  Gemini CLI or SDK fallback is introduced.
- Refresh version-bound project-estimation bootstrap data, retaining calibration
  warnings and unknown numeric quotas. Pricing covers exact configured models
  without borrowing prices for unknown models. The collection policy removes
  unconfirmed Google 3.7 records and retains verified 3.6 records.

#### Why
- Make bounded delegation predictable, reduce worker time spent searching for
  unavailable test environments, and prevent review findings from encoding an
  unsupported SDK contract.
- Help diagnose native startup failures without exposing credential material or
  changing route admission, retry behavior, or response interpretation.
