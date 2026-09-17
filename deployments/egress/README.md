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
of this Goal. The image includes `ovs-vsctl` from Debian's `openvswitch-switch`
package and checks both required commands during the build; its entrypoint runs
only the Network collector, not an OVS daemon.
`scripts/render-node-facts --nodes nodes.json --image <image@sha256> --ovs-socket-uid <verified-uid>`
renders manifests only, from the intended cluster's captured node UID inventory.
The output creates one small probe per node, with a separate ServiceAccount that
can GET only that Node and GET/PATCH only its precreated facts ConfigMap. It cannot
write `kcn-config`, nodes, routes, or other probes' ConfigMaps. Node replacement
requires a new reviewed manifest; an old collector fails closed on changed UID.

The probe enters the node network namespace via `hostNetwork`, reads `/sys`,
`ip -j` link/address/IPv4+IPv6 route facts, and read-only OVS Interface listings.
For OVS-managed physical devices it also reads the actual containing bridge,
kc bridge external IDs and `ovn-bridge-mappings`. These prove existing kc wiring;
the node's managed-device annotation alone is insufficient. Update collectors
before relying on the additional proof; older documents with no bridge proof
cannot make a managed device ready.
The OVS socket path and numeric owner UID must match the actual nodes; read them
with `stat -Lc '%u:%g:%a' /var/run/openvswitch/db.sock` before rendering. Select only
nodes with the specified socket owner, or render separate groups. The collector
runs as that UID and drops all Linux capabilities, without privileged mode or host
PID access. Root with all capabilities dropped cannot connect to another UID's
owner-writable socket. Do not change the shared socket's mode or add DAC override
capabilities to bypass this check. Network mutations are absent from the
collector's commands. Missing OVS facts do not
imply an unused interface. Each collection has a 10-second deadline and runs at
15-second intervals; failures leave the old collection timestamp unchanged.
Network rejects facts older than 60 seconds, duplicate/missing sources, changed
node UID, assigned non-link-local IPs, management/default-route interfaces
(including their internal OVS bridge), virtual interfaces, foreign masters or
bridges and incompatible VLAN occupancy. Correctly configured kc-managed devices
can be registered through the existing platform API after complete verification;
they retain their actual managed status and their existing physical configuration.

Applying the probe manifests only discovers facts. Adopting a device is an
explicit platform operation. The registration uses the existing UID/resourceVersion
guarded binding annotation; it does not rewrite `managedDevices` for a pre-managed
device. A foreign binding cannot be overwritten. Exact admission, observation and
retirement rules live in [the specification](../../docs/specs/vpc-snat.md#41-underlay-的网卡发现与二层网络).
Live deployment and physical verification require the current task's authorization;
their actual status is recorded in the execution ledger.

## Intranet pools

[Intranet pool prerequisites](intranet.md) covers the default VPC identity,
existing destination routing ranges, independent evidence and allocation gates.
