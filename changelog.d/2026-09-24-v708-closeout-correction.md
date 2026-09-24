### Documentation

- Correct the v7.0.8 closeout evidence for two installed canaries: their first attempts, run under concurrent host load, timed out with zero output, and their provider-dispatch status is unknown -- neither attempt is counted as qualified or failed. A separately-issued, isolated request for each is recorded as its own qualification evidence instead of being described as resolving the earlier attempt.
- Add real, separately-run, explicitly-targeted installed Claude `context.documents.intent` qualification evidence, replacing the prior claim that staged qualification alone stood in for an installed canary.
