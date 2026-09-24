### Fixed

- The coordinator now repairs request-construction mistakes that previously failed before any provider started: missing or stale wire digest, omitted defaults, field aliases, value synonyms, over-limit deadlines, and fenced JSON. Every repair is reported in the result's `repairs` field.
- A read-only repository request without `native_restrictions` is bound to the repository its payload names, or the caller's repository, instead of running in an empty temporary directory where the reviewer could not read the source. Code-generation actions are never auto-bound. A supplied directory's identity is read at dispatch.
