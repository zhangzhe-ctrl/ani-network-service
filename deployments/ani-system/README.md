# ani-system deployment (governance mode)

RBAC and identity for the `ani-resource-service` instance that serves governance.

## Why the ServiceAccount is not optional

The process builds its Kubernetes client from `ANI_NETWORK_KUBECONFIG`. In-cluster
that value is intentionally empty, so `internal/data/network/kc.go`
(`OpenKCProvider` -> `rest.InClusterConfig`) falls back to the pod's
ServiceAccount. The ServiceAccount is therefore the *only* identity the provider
has, and it must be bound to the ClusterRoles below.

Using the namespace `default` ServiceAccount instead — as the first ani-system
rollout did — fails two ways at once:

- the grant applies to every pod in the namespace, not just this one; and
- it is invisible to `deployments/*/network-rbac.yaml` review, so a fresh cluster
  reproduces the outage.

The symptom of a missing grant is not a clean 403 in the API. A 403 from the
provider client is classified `ProviderTemporary` and surfaced as
`PROVIDER_UNAVAILABLE`: VPC creation stays `provisioning`, and subnet creation is
refused with `412 PARENT_NOT_READY` because the parent VPC never gets a fresh
observation.

## Apply

Apply the feature roles first, then the identities that bind them.

```bash
kubectl apply -f deployments/egress/network-rbac.yaml
kubectl apply -f deployments/load-balancer/network-rbac.yaml
kubectl apply -f deployments/ani-system/networking-rbac.yaml
```

Then point the Deployment at the ServiceAccount (this is the step that was
missing, and it rolls the pod):

```bash
kubectl -n ani-system patch deployment ani-resource-service \
  --type merge \
  -p '{"spec":{"template":{"spec":{"serviceAccountName":"ani-resource-service"}}}}'
```

## Verify

```bash
kubectl -n ani-system auth can-i list vpcs.networking.kubercloud.com \
  --as=system:serviceaccount:ani-system:ani-resource-service
```

Then confirm a real write converges end to end: create a VPC, wait for
`state=available`, create a subnet inside it, and check the kcn `Subnet` CR
reports `READY=True` with a gateway assigned. `PROVIDER_UNAVAILABLE` means the
grant is still not reaching the pod.
