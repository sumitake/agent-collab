#!/usr/bin/env python3
"""Public release identity anchor for the native runtime.

The Developer ID Team ID is intentionally independent of the mutable runtime
manifest.  It must be set to the operator-owned ten-character Apple Team ID in
a reviewed source change before an activation release can pass.  Empty means
fail closed; it is never populated from an environment variable or manifest.
"""

EXPECTED_DEVELOPER_ID_TEAM = "36UFP9KY4T"
