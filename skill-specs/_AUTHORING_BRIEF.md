# Skill-spec authoring brief

Author every collaboration skill for a dynamically resolved primary and an
independent reviewer or worker chosen by central policy.

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
- keep Claude asynchronous inbox-only;
- never weaken the plan/build or advisory/build authority boundary.

Run the generator and deterministic validation commands in the repository
development guide. The generated file under
`plugins/agent-collab/skills/<name>/SKILL.md` must match the spec renderer.
