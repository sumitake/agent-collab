---
name: red-team
version: {{ skill_version }}
{{ red_team_defaults_block }}
description: Task {{ verifier_agent }} with actively breaking a system, API, validation layer, prompt pipeline, policy boundary, or logic flow that {{ primary_agent }} (or the user) has just built. The verifier generates concrete adversarial inputs — exact strings, payloads, scenarios — designed to bypass controls, crash the system, or trigger misbehavior. Use when the user says "red-team this," "try to break this," "attack this," "stress-test this," "adversarial test this," "find ways this could fail," "what could go wrong with this validation," "break my parser," "break my prompt," "find bypasses," or similar break-this-system framings. Also offer this proactively when {{ primary_agent }} has just shipped or is about to ship a security boundary, input validation, authentication flow, content-moderation policy, prompt pipeline, rate-limiting rule, payment validator, or any control surface where the cost of an undiscovered bypass is high.
---

# Red team — adversarial input generation by the cross-family agent

Red-teaming is **active and adversarial**: the verifier's job is not to *look for* defects in the artifact (`code-review` does that), but to **generate specific inputs that break it**. The output is concrete, ready-to-use attack vectors — exact payloads, exact malformed inputs, exact prompt-injection strings — not generic "the parser might be vulnerable to malformed input" observations.

The cross-family setup is load-bearing for the same reason it is in `code-review`: {{ primary_agent }} (the author, in the {{ primary_family }} family) shares blind spots with itself — it will not generate the adversarial inputs that exploit its own assumptions. {{ verifier_agent }} ({{ verifier_family }} family) brings different priors on what looks "obviously safe," which is exactly the set of inputs likely to be unguarded.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "red-team this," "try to break this," "attack this," "stress-test this," "adversarial test this," "find ways this could fail," "what could go wrong with this validation," "break my parser," "break my prompt," "find bypasses," "what would an attacker do here."
- **{{ primary_agent }} has just built a security boundary** — auth flow, authorization rule, rate limiter, IP allow-list, RBAC policy, signature verifier, input sanitizer.
- **{{ primary_agent }} has just built input validation** — form validator, API request schema, query parser, file upload checker, deserializer.
- **{{ primary_agent }} has just built a prompt pipeline** — system prompt, tool-use loop, agent guardrails, content moderation policy.
- **The user is about to ship a control surface where bypasses are expensive** — payment-validation logic, fraud-detection rule, content-moderation filter, regulatory-compliance check, clinical-decision-support guardrail.

## When to skip

Skip this skill when:

- **The artifact is not a control surface.** Red-teaming a UI-only change or a documentation update produces nothing useful.
- **The artifact has no defined adversary.** Red-teaming a draft email or a brainstorm output is the wrong tool — the "attacker" has no concrete objective. Use `second-opinion` for general critique.
- **The user wants passive bug-finding.** That is `code-review`'s job (defect-class surfacing). Red-team is for generating attack inputs against a specific surface.
- **The user has already red-teamed this exact surface** and is asking for another pass without changes. Coverage saturation is real; additional passes return increasingly speculative inputs.

<!-- verifier-independence:start -->
## Verifier independence (functional contract)

A review is independent only when its observed author family differs from both
the immutable primary snapshot and artifact-author snapshot. The shared policy
recognizes Anthropic, Google, OpenAI, xAI, Zhipu, and genuinely unknown lineage;
OpenCode itself is a transport, not a family. Resolve through `coordinator.py`
immediately before every call. Governance fails closed when either snapshot is
unknown or no distinct-family advisory route is eligible. Non-governance work
may proceed only with an independence warning. Claude is ineligible for these
review and governance routes; its only managed route is document intent, and
host-owned async coordination is separate.
<!-- verifier-independence:end -->

## Procedure

### 1. Describe the system precisely

Pin down what the verifier is supposed to break. Give it:

- The **specification** — what the system is supposed to do, what inputs it accepts, what controls it enforces.
- The **code or rule definition** — the actual implementation. The verifier needs to see the literal artifact, not a reference to it.
- The **threat model** — who is the assumed adversary? An unauthenticated external attacker has different leverage than a logged-in user; a privileged insider has different leverage than either. The threat model frames which attack vectors are in scope.
- The **success criterion** — what counts as "broken"? A bypass (input that should be rejected is accepted), a crash (input that triggers an unhandled exception or DoS), a misbehavior (input that produces unintended output without crashing), or all three.

Vague descriptions produce vague attack lists. The fifteen seconds spent framing the system pays off across the entire generated set.

### 2. Assign the red-team objective

Be specific about what to break:

- "Generate 10 inputs that bypass this validation."
- "Generate 10 prompts that jailbreak this system instruction."
- "Generate 10 payloads that crash this parser."
- "Generate 10 sequences that desynchronize this rate-limiter's per-IP counter."

A focused objective produces focused output. "Find security issues" produces a generic list; "find inputs that bypass the email-validation regex" produces 10 concrete strings.

### 3. Call the verifier

Submit the sealed red-team role through `{{ mcp_tool_ask }}` using the
documented closed coordinator request below. Central policy chooses an eligible
independent reviewer. Frontmatter `effort` is host guidance and is never a
coordinator request field.

```json coordinator-request
{"request_id":"red-team-1","logical_action":"review.repository","quality_profile":"frontier","effort_class":"maximum","target_agent":null,"timeout_ms":120000,"prompt":"Attack the supplied repository artifact using the red-team contract below.","repo_root":"<canonical-repo-root>","expected_repo_head":"<verified-repo-head>"}
```

Use this prompt template for adversarial content. The signed descriptor's
`review_findings` schema is the sole output contract; do not add a second JSON,
JSONL, heading, or trailing-prose envelope:

```
You are a red-team agent. Your objective: break the [validation logic / API contract / parser / prompt pipeline / policy] below. Generate exactly N adversarial inputs — exact strings, payloads, or scenarios — designed to bypass, crash, or trigger misbehavior in the target system.

Threat model: [unauthenticated external attacker / authenticated low-privilege user / privileged insider / model-output adversary / ...]
Success criterion: [bypass / crash / misbehavior — choose one or "any of the three"]

Record each viable adversarial input, predicted result, and mechanism in a
descriptor-owned finding message. If fewer than N meet the criterion, return
only the viable findings and explain the shortfall in the artifact summary.

--- TARGET ---
[Specification + code/rule definition]
```

An `invalid_final` result is terminal for this request. Surface the failure
explicitly; do not fabricate an artifact around prose and do not replay the
coordinator request. It may signal a content-policy guardrail and must remain
visible as evidence of the verifier's limits.

### 4. Verify each finding, then close the loop

Adjudicate each adversarial finding before relaying it to the user:

1. **Actually test it.** Run the input against the real system (or a faithful local reproduction). If the input does NOT in fact bypass / crash / misbehave as claimed, drop it from the user-facing report — the verifier hallucinated an attack vector. Hallucinations are common in red-teaming because the verifier is generating *plausible* inputs without ground-truth verification.
2. **Categorize by attack class.** Group findings — "all five inputs in this set exploit the unicode-normalization gap," "three exploit the integer-overflow on the count field." Class-level patterns are more useful than per-input lists for fix prioritization.
3. **Score by severity and exploitability.** A bypass requiring privileged insider access ranks differently from a bypass exploitable by an anonymous external request.
4. **Recommend fixes.** For each verified attack class, propose a concrete defense — the input normalization that closes the unicode-gap, the bounded-integer type that prevents the overflow, the explicit rate-limiter reset that prevents the desync.
5. **Surface an empty-findings result accurately.** If the summary says no
   viable input met the objective, report that without treating it as proof of
   security; it is failure-to-find, not a soundness guarantee.

End with a synthesis paragraph: which attack classes are load-bearing (the user must fix before deploying), which are noise (hallucinations or extremely-low-exploitability), and a recommendation on whether the surface is ready as-is or needs revision.

## Examples across domains

Red-teaming applies wherever a control surface exists with adversarial inputs. A representative sample:

| Domain | Control surface under attack | Example adversarial-input categories |
|---|---|---|
| Backend / web | Login-throttling rule (5 attempts per IP per 5 min) | Per-IP counter desync via X-Forwarded-For spoofing; per-user counter desync via case-variant email; reset-via-password-recovery side channel |
| API engineering | Webhook signature verifier for a payments integration | Timing-oracle on the HMAC compare; truncated-signature acceptance; replay of a stale-but-valid signature; algorithm-confusion downgrade |
| Auth / identity | Session-token expiration logic | Clock-skew exploit; refresh-token re-use after rotation; concurrent-refresh race producing two valid tokens |
| Input validation | Email-validation regex on a sign-up form | RFC-5322-edge-case bypasses; unicode-confusable bypasses; quoted-local-part with control characters; max-length bypass via punycode expansion |
| Prompt engineering | System prompt for a customer-service agent (must refuse refund requests outside policy) | Direct-injection ("ignore prior instructions"); indirect-injection via injected document content; role-confusion ("I am the system administrator"); language-switch attack; legitimate-frame attack ("for testing only") |
| Policy / compliance | Content-moderation classifier for an LLM output | Obfuscation via stylization (zero-width joiners, leetspeak); language-switch evasion; legitimate-wrapper attack (cite-as-quoted-research); multi-turn slow-walk |
| Financial software | Fraud-detection rule for high-value transfers | Per-account threshold split-payment; geographic-pattern evasion via VPN cycling; round-trip via legitimate counterparty |
| Clinical software | Drug-interaction warning rule | Generic-name vs brand-name mismatch evasion; combination drug exploitation (component A + component B not the combined product); dose-form ambiguity (extended-release vs immediate-release) |
| Embedded / IoT | Firmware-update signature checker on a smart-thermostat | Signature-stripping with valid-checksum padding; rollback-to-vulnerable-version exploit; partial-write power-fail to forced-recovery-mode |
| Distributed systems | Leader-election protocol in a coordination service | Network-partition-induced split-brain; clock-jump-induced false leader; message-reordering-induced log divergence |

The signed artifact schema and threat-model + success-criterion framing stay constant across domains; the attack categories shift to match the surface.

## Anti-patterns

- **Vague "is this secure?" prompts.** That is `code-review` framing, not red-team. Red-team requires a specific objective ("bypass this validation," "crash this parser") and produces specific attack inputs.
- **Treating the attack list as exhaustive.** It is a productive sample, not a proof of security. The absence of a vector in the list does not mean it is undefended.
- **Skipping the actually-test-each-input step.** Hallucinations are common; relaying unverified attack claims wastes the user's time and may mislead them about real exposure. Test in a local reproduction before reporting.
- **Asking the verifier to also fix the vulnerabilities.** Generate attacks (this skill) and propose defenses (the user or {{ primary_agent }} acts on them) are separate steps. The verifier's job is to find attacks, not write the fixes — those are likely to be same-family-correlated patches.
- **Using economical/minimal.** Adversarial creativity benefits from depth; use frontier/maximum so the review goes beyond obvious, commonly listed inputs.
- **Skipping the verifier-independence check** when the artifact came from a {{ verifier_family }}-family agent. Same-family red-teams produce inputs the author would have anticipated.
- **Replaying a malformed request.** Treat malformed output as the terminal typed
  failure returned by the managed runtime. Surface it instead of issuing a
  second request or fabricating an artifact.
- **Treating an empty findings list as a security proof.** It is the verifier's failure-to-find, not a soundness argument. The system may still have undefended classes the verifier did not explore.
- **Running red-team on artifacts with no adversarial framing.** A draft email or a brainstorm output has no adversary; the exercise produces nothing useful.
- **Re-running on a surface that has already been red-teamed without changes.** Coverage saturation is real; additional passes return increasingly speculative inputs.
