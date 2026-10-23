# External-method contract review case

For a fresh reviewer evaluation, copy only `sdk.py`, `case_a.py`, and
`case_b.py` into a disposable repository. Apply the candidate review skill's
guidance and ask for a source-grounded review of both callers against this
supplied SDK. Do not provide this rubric to the reviewer. Retain the complete
native response and source identity; adjudicate it manually. No keyword or
verdict classifier establishes a pass.

The review should preserve case A's string reads. It should identify case B's
UUID read arguments as a real serialization error, grounded in `get` and
`list` passing values unchanged into `_command` and `json.dumps`. `create`
accepts UUID objects and explicitly converts their bytes; its different
contract cannot establish the read methods' argument types. Assertions that
require UUID objects for the reads would encode the wrong contract.

`test_sdk_method_contract_fixture.py` proves these fixture behaviors with the
real standard-library JSON serializer. It validates the example, not an LLM's
review quality. A reviewer evaluation remains a separate observation.
