agent-collab 4.5.0 routes the packaged OpenCode default through
`opencode-go/glm-5.2`, recognizes
Kimi as Moonshot-family provenance, and adds an opt-in
`AGENT_COLLAB_OPENCODE_PROVIDER=opencode-go` host guard that rejects standard
metered OpenCode Zen models, malformed provider policy, namespace lookalikes,
and late policy drift before runtime launch.
