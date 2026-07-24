# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 4.x | Yes |
| Earlier releases | No |

Policy-only releases contain no native runtime. When an activation release is
available, only the artifact shipped with a supported release is in scope.

## Report a vulnerability privately

Do not open a public issue or pull request for a suspected vulnerability,
credential exposure, source-boundary breach, or release-artifact problem. Use
[GitHub private vulnerability reporting](https://github.com/sumitake/agent-collab/security/advisories/new).

Include the affected release tag, commit, host and plugin manager; impact; the
smallest safe reproduction; observed versus expected behavior; sanitized public
logs; and, for a native artifact, its published digest and signature status.

Do not attach secrets, private implementation material, native binary dumps, or
decompiled source. Reference a public release tag and digest instead. If private
reporting is unavailable, open a public issue containing only a request for a
private contact channel and no vulnerability details.

Reports are triaged privately. Coordinated disclosure timing is agreed with the
reporter after impact and remediation are understood.
