# Service repository guidance

This service owns its generated runtime source. It has no runtime dependency on
the layout that created it.

Read `docs/START-HERE.md` for the current document index, then `CONTEXT.md` and
the applicable spec/ADRs before changing business behavior. Current execution
state lives only in `docs/execution/status.md`. A design or plan is not evidence
that its behavior has been implemented or verified; follow the user's actual
task scope and authorization.

## Boundaries

- `cmd/ani-network-service` is the explicit composition root.
- `internal/service` adapts inbound transport contracts to use cases.
- `internal/biz` owns domain concepts, behavior, use cases, and required ports;
  it must not import Kratos, protobuf, transports, or storage drivers.
- `internal/data` implements outbound ports and owns infrastructure-specific
  code. Add an adapter only when a vertical slice needs it.
- `internal/server` owns transport and cross-cutting runtime wiring, not
  business rules.

Prefer framework capabilities over local replacements. Do not introduce a
shared ANI runtime module, generalized YAML exception registry, or technology
switches unrelated to a real slice. Generate protobuf output through the pinned
workflow and run `make verify` before committing.

## Execution location

- Prefer SSH host `ubuntu` for compilation, full test suites, image builds,
  dependency-tool builds, and PostgreSQL integration tests. Keep local work to
  editing, inspection, and lightweight checks when the remote is available.
- The user permits local fallback when remote execution is unavailable. Record
  the reason, actual execution host, source snapshot, commands, and results;
  do not silently mix local and remote evidence.
- Follow `docs/remote-execution.md` for isolated source transfer, tool versions,
  and artifact handling. Never overwrite another remote working tree or copy
  credentials as part of a source snapshot.

## Documentation

- Root `README.md` is the project/quick-start entry, `AGENTS.md` contains brief
  engineering rules, and `CONTEXT.md` contains domain vocabulary only.
- `docs/START-HERE.md` is the single documentation index. Keep formal specs in
  `docs/specs/`, decisions and rationale in `docs/adr/`, implementation order in
  `docs/plans/`, and current progress plus evidence in `docs/execution/`.
- Each rule has one authoritative home; link to it instead of copying contract,
  state-machine, schema, or progress tables into multiple files. Do not place a
  second current spec or formal execution ledger under `.scratch/`.
- Use canonical domain names in contracts, implementation, tests, and docs.
  Keep provider terminology in infrastructure adapters and their contracts.
- Mark superseded documents with a replacement link. Record source snapshots,
  actual commands, and `pass` / `fail` / `not_verified` separately from plans.
- Keep local document links relative and verify targets/anchors after changes.
  Cross-repository source links are point-in-time evidence, not build/runtime
  dependencies or authorization to change those repositories.
