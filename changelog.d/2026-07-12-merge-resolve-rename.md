### Breaking

- Rename the public `ai-merge-resolve` skill to `merge-resolve`, including its generated command and auto-apply policy filename. Existing installations must invoke `/agent-collab:merge-resolve` and rename `.claude/ai-merge-policy.yaml` to `.claude/merge-resolve-policy.yaml` when that opt-in file is used.
