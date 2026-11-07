# ADR 0001 — Standard-library Python and additive user integration

Status: accepted for the first functional slice, 2026-11-07.

Amendment: [ADR 0002](0002-volume-controller-service-adapter.md) adds one optional,
hash-pinned pure-Python WebSocket dependency for the observed plugin service.
The OAuth/native-launch core continues to use the standard library.

Problem: the selected DeckBridge checkout has an empty Git repository, while a
working Bash/Python installer and its untracked user changes live in the sibling
`streamdeck-linux` directory. The installed copy also differs from that checkout.
Wine and Python are available; Rust/Cargo and MinGW are absent.

Options: migrate/copy the old installer immediately; install a new Rust toolchain;
or add a small isolated host service alongside the audited installation.

Decision: use typed Python dataclasses and the standard library for a small daemon,
with Bash/Wine remaining responsible for the original installation. Add a
separate idempotent user integration installer that consumes an explicitly
supplied existing prefix. Do not touch either previous installer copy or rerun
its MSI path. Pin development tooling in a repository-local virtual environment.

Trade-offs: Python runtime validation and tests enforce the wire contract; static
types alone are not a complete proof. This avoids new system dependencies and
unnecessary migration of user changes. A future native Win32 shim needs an
ABI-appropriate compiled toolchain, and a future Rust daemon remains possible
without changing the v1 IPC boundary if there is a measured need.

Native actions use allowlisted argv in transient user services. Callback routing
uses existing Wine/application instance behavior, with observable receipt checked
separately. No generic DLL shim is justified for the missing Linux MIME boundary.
