# Stage and rollback lane

This note captures the first operational expectations for the Fedora Asahi + Nix control-plane lane.

## Required flow

1. build candidate inputs
2. stage candidate in an isolated lane
3. run smoke checks
4. activate on host only after stage success
5. verify host health
6. keep or roll back

## Rollback surfaces

- generation rollback
- image rollback
- snapshot rollback

## Non-goal

This document does not yet prescribe the exact shell tooling. It exists to keep the operational sequence stable while the implementation modules are still being built out.
