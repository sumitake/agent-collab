- The signed runtime bundle can now be distributed by committing it to the public
  git repository, so the documented marketplace install (`/plugin marketplace add`)
  delivers a working activation build under any operator umask — including umask
  002, whose group-writable checkout the previous exact-`0o500` and safe-envelope
  checks both rejected. The plugin checkout is now treated as a trusted **source**
  under the trust-the-checkout model: the host already executes the plugin's Python
  control plane from the same tree, so a peer who can write the checkout already
  owns the verifier, and the source permission-mode rejection (which blocked normal
  clones) is dropped in favor of a floor that requires owner read+execute and no
  special bits while tolerating group/other bits. Content integrity is unchanged —
  per-member SHA-256, Developer-ID signature, notarization, and Mach-O checks are
  untouched — and the privately-extracted **broker store** keeps its exact `0o500`
  check. `build_plugin_archive` now packages the committed in-tree runtime (with
  optional git-`HEAD` `100755`/`100644` provenance binding it to the release tag)
  in addition to the external sealed `--bundle-source` handoff. (agent-collab 4.1.1)
