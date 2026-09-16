### Fixed

- Use the OS account's canonical home for native execution and preserve SSH
  session markers so providers retain their own login behavior. Request files
  remain temporary; login profiles are not copied.
- Clarify that native recovery stays within the original invocation and that
  existing operator authorization persists across tool steps in the same scope.
