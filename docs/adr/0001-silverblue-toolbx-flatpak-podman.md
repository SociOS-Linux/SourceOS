# ADR 0001 — Silverblue + Toolbx + Flatpak + rootless Podman

Status: proposed

Decision:
- Use Fedora Silverblue (GNOME) as workstation base.
- Use Toolbx for dev environments.
- Use Flatpak for GUI apps.
- Use rootless Podman for services.

Why:
- Immutable base reduces drift.
- User-space isolation avoids breaking system environments (PEP 668-style issues).
- Sandboxed GUI reduces app-level blast radius.

Consequences:
- We must provide first-class tooling to make user-space ergonomics excellent.
