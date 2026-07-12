# Shared skill specifications

The 26 non-underscore Markdown files in this directory are the editable source
for their matching `plugins/agent-collab/skills/*/SKILL.md` files. There is one
output package and no alias or preset generation.

Use placeholders only for dynamic role language, defaults, and effort hints.
Provider commands, binary paths, authentication mechanics, model-family policy,
and fallback logic do not belong in a skill spec; the unified runtime and host
policy own them.

Command substitutions contain only the bare command. Put explanatory prose and
Markdown code delimiters in the spec so rendering cannot create nested
backticks or duplicate invocation language.

Workflow:

1. Edit the relevant spec.
2. Run `python3 scripts/build_skills.py`.
3. Run `python3 scripts/build_skills.py --check`.
4. Validate frontmatter and repository tests.

Generated skill files are not direct edit targets. Package-specific allowlists
should normally be absent; the sole allowed package name is `agent-collab`.
