### Fixed

- Connect the existing progress channel for descriptor-admitted work so the
  outer client does not terminate a provider that is still making progress.
- Accept a null optional deadline consistently with omission, and preserve
  collected content if local I/O fails later.
- Report local client exceptions as `client_error`, without claiming provider
  unavailability, authentication failure, or an unconsumed attempt.
- Preserve configured native CLI login, configuration, and catalog locations
  while continuing to exclude credential values and inline API configuration.
- Generate caller guidance with current manifest and filesystem identities,
  EOF-delimited input, workload-appropriate work units, and no accidental
  provider pin or competing outer timeout. Planning proves route eligibility,
  not provider health or authentication.

### Changed

- Prepare the agent-collab 7.0.3 candidate for runtime 5.0.5 and wire schema
  12. This change requires both signed runtime handoffs before release
  qualification.
