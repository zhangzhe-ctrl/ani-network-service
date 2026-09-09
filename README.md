# ani-network-service

Module: `github.com/zhangzhe-ctrl/ani-network-service`

This repository was generated from ANI's pinned Kratos layout. It is an
independent source snapshot: builds and runtime do not require the layout.

本仓库承接 ANI Network 独立服务。当前仅完成 Kratos 运行骨架初始化；
VPC/Subnet、sqlc、无 RLS 多租户持久化及 Gateway 接线尚未实现。
继续讨论前请阅读 [开发起点与交接](docs/START-HERE.md)。

`THIRD_PARTY_NOTICES.go-kratos-layout.txt` preserves the upstream template's
MIT notice. This generated repository intentionally has no project `LICENSE`;
its owner must make that choice before publication.

## Local commands

```bash
make tools
make verify
go run ./cmd/ani-network-service -conf ./configs
```

After the initial source commit, run `make supply-chain-tools` and `make audit`;
review and commit `docs/scaffold/bom.cdx.json`. CI deliberately fails when that
runtime SBOM is missing or stale and reruns the vulnerability, secret,
notice-integrity, and license-evidence gates.

The committed listeners are loopback-only local defaults. Override them through
the typed `ANI` environment configuration when the deployment design is added.

## Runtime shell

- Kratos lifecycle with graceful shutdown.
- gRPC and a separate admin HTTP server.
- Structured redacted logs, tracing, metrics, and middleware.
- `/healthz` reports process liveness.
- `/readyz` reports only completion of the local runtime start hook; add checks
  for real dependencies when the first vertical slice introduces them.
- `/metrics` exports the local Prometheus registry.

There is intentionally no sample domain, persistence, broker, auth, provider,
container, or deployment configuration.
