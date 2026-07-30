### Changed

- Express the two deliberately-insecure test fixtures with `os.chmod` and an inline CodeQL suppression carrying a stated rationale, instead of routing them through `Path.chmod` to sidestep the query's modeled sink. The permissive mode in each is the input under test — the assertion is that the resolver refuses the artifact — and no production path sets a permissive mode. This states the intent where a reader will see it, rather than depending on which call shape the scanner happens to model.
