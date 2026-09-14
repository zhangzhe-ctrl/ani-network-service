# Egress runtime prerequisites

The existing Network process registers the tenant and platform gRPC services and
runs their durable work through the existing resource worker. It requires the
additional reads/writes in [network-rbac.yaml](network-rbac.yaml). Adapt its
ServiceAccount subject to the actual deployment; this template is not applied by
any test or build script. No actor or tenant metadata header grants egress access.
A trusted ingress must explicitly supply `biz.EgressCaller`; until that integration
is installed, egress RPCs deny access. Controlled test injection is not IAM proof.

## Node facts

Build the same source snapshot's binary on `ubuntu`, then build
[NodeFacts.Dockerfile](NodeFacts.Dockerfile) there if deploying the optional probe.
Record the resulting image ID/digest and tool versions. Do not publish it as part
of this Goal. `scripts/render-node-facts --nodes nodes.json --image <image@sha256>`
renders manifests only, from the intended cluster's captured node UID inventory.
The output creates one small probe per node, with a separate ServiceAccount that
can GET only that Node and GET/PATCH only its precreated facts ConfigMap. It cannot
write `kcn-config`, nodes, routes, or other probes' ConfigMaps. Node replacement
requires a new reviewed manifest; an old collector fails closed on changed UID.

The probe enters the node network namespace via `hostNetwork`, reads `/sys`,
`ip -j` link/address/IPv4+IPv6 route facts, and read-only OVS Interface listings.
The OVS socket path must match the actual node. It drops Linux capabilities and
has no privileged mode or host PID access. Root is used for the local OVS socket;
network mutations are absent from its command allowlist. Missing OVS facts do not
imply an unused interface. Each collection has a 10-second deadline and runs at
15-second intervals; failures leave the old collection timestamp unchanged.
Network rejects facts older than 60 seconds, duplicate/missing sources, changed
node UID, assigned non-link-local IPs, management/default-route interfaces,
virtual interfaces, masters, OVS/KC-managed interfaces and VLAN occupancy.

Applying the probe manifests only discovers facts. Adopting a device is an
explicit platform operation. In this Goal real physical devices are not adopted;
physical/OVS socket deployment verification remains `not_verified`.

## Intranet pools

[Intranet pool prerequisites](intranet.md) covers the default VPC identity,
existing destination routing ranges, independent evidence and allocation gates.
