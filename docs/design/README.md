# Design and review evidence

This directory retains design artifacts and adversarial review records. These
files explain why current release-safety code has its shape, but they are not a
substitute for merged source, tests, package manifests, or the public
[architecture handbook](../architecture/README.md).

## How to use this directory

- **Design of record** means current source explicitly cites the document for a
  defined contract. Read only the cited section/version and verify it against
  code and tests.
- **Superseded design** preserves earlier reasoning. Later sections within the
  same file may override earlier sections.
- **Historical review** records objections and verdicts from a past design
  cycle. A review verdict does not describe current implementation by itself.

## Registry

| Document | Classification | Current use |
| --- | --- | --- |
| [`release-cut-pipeline-v2-saga-design.md`](release-cut-pipeline-v2-saga-design.md) | mixed design-of-record and superseded draft | `scripts/release_tag_contract.py` cites the converged v3 release-saga architecture. The filename and opening v2 status are historical layers; inspect the cited v3 section and current tests. |
| [`pr4-cut-release-activation-design.md`](pr4-cut-release-activation-design.md) | mixed design-of-record and superseded versions | Current tag-contract source cites V3/V9. Earlier V0–V10 text remains historical where later sections conflict. |
| [`reconciliation-contract-correction.md`](reconciliation-contract-correction.md) | historical design intervention | Records the stop-and-redesign tripwire that preceded the broader release saga. It is not the current standalone release contract. |
| [`reviews/reconciliation-plan-adversarial-review-1.md`](reviews/reconciliation-plan-adversarial-review-1.md) | historical review | First adversarial review of the reconciliation plan. |
| [`reviews/pipeline-v2-adversarial-review-2.md`](reviews/pipeline-v2-adversarial-review-2.md) | historical review | Second review round for the release pipeline design. |
| [`reviews/pipeline-v3-adversarial-review-3.md`](reviews/pipeline-v3-adversarial-review-3.md) | historical review | Third review round and remaining objections at that snapshot. |

## Precedence

For current behavior, use this order:

1. merged source and focused tests;
2. public manifests, schemas, and release evidence;
3. normative governance and security documents;
4. explicitly cited design-of-record sections; and
5. historical designs and review records for rationale only.

When adding a design or review file, update this registry and state whether it
is proposed, current design-of-record evidence, superseded, or historical.
