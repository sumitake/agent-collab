### agent-collab 4.0.5 - Gemini governance proof v2

- Validate Gemini governance evidence against the provider runtime `2.0.0`
  proof contract `2` tuple instead of conflating it with the public bundle
  manifest contract, and require governance response provenance to identify
  that same compatible runtime while rejecting legacy, crossed, and
  mixed-provenance version tuples.
