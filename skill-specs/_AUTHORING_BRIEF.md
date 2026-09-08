# Skill-spec authoring brief

Author every collaboration skill for a dynamically resolved primary. Where
independence matters, require the caller to establish the primary, artifact
author, and reviewer lineages before accepting a response as independent
governance evidence; routing does not establish that fact.

Required frontmatter:

- stable neutral `name`;
- semver `version`;
- description with explicit quoted user triggers and a situational/proactive
  trigger.

Required body properties:

- preserve the role's semantic method and output contract;
- treat delegated output as untrusted;
- keep governance independence explicit where relevant;
- use the managed runtime abstraction rather than a provider command;
- keep executable substitutions as bare commands without prose or Markdown;
  the spec owns the surrounding sentence and code backticks;
- state that unavailable native routes return typed unavailable;
- keep Claude action-scoped: managed only for document intent, ineligible for
  review, governance, repository, and code-generation actions, with host-owned
  asynchronous coordination treated as a separate surface;
- never weaken the plan/build or advisory/build authority boundary.

Run the generator and deterministic validation commands in the repository
development guide. The generated file under
`plugins/agent-collab/skills/<name>/SKILL.md` must match the spec renderer.
