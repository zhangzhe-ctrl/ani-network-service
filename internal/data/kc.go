package data

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data/sqlcgen"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

var kcVPCs = schema.GroupVersionResource{Group: "networking.kubercloud.com", Version: "v1", Resource: "vpcs"}
var kcSubnets = schema.GroupVersionResource{Group: "networking.kubercloud.com", Version: "v1", Resource: "subnets"}
var namespaces = schema.GroupVersionResource{Version: "v1", Resource: "namespaces"}

const ownerLabel = "network.ani.io/managed-by"
const tenantLabel = "network.ani.io/tenant-id"
const resourceLabel = "network.ani.io/resource-id"
const bindingLabel = "network.ani.io/binding-id"

// KCProvider implements only the fixed networking.kubercloud.com/v1 VPC
// contract. It does not import the kc repository or operate on OVN.
type KCProvider struct {
	repository *Postgres
	client     dynamic.Interface
}

func OpenKCProvider(repository *Postgres, kubeconfig string) (*KCProvider, error) {
	var config *rest.Config
	var err error
	if kubeconfig == "" {
		config, err = rest.InClusterConfig()
	} else {
		config, err = clientcmd.BuildConfigFromFlags("", kubeconfig)
	}
	if err != nil {
		return nil, fmt.Errorf("Kubernetes credentials/configuration could not be loaded")
	}
	return NewKCProvider(repository, config)
}

func NewKCProvider(repository *Postgres, config *rest.Config) (*KCProvider, error) {
	if repository == nil || config == nil {
		return nil, fmt.Errorf("PostgreSQL mapping and Kubernetes configuration required")
	}
	copy := rest.CopyConfig(config)
	copy.Timeout = 10 * time.Second
	copy.UserAgent = "ani-network-service/net-01"
	client, err := dynamic.NewForConfig(copy)
	if err != nil {
		return nil, fmt.Errorf("Kubernetes client configuration invalid")
	}
	return &KCProvider{repository: repository, client: client}, nil
}

func (p *KCProvider) binding(ctx context.Context, target biz.ProviderTarget) (sqlcgen.NetworkProviderBinding, error) {
	value, err := p.repository.queries.GetBinding(ctx, sqlcgen.GetBindingParams{TenantID: target.TenantID, VpcID: target.ResourceID})
	if err != nil {
		return value, &biz.ProviderError{Kind: biz.ProviderTemporary, Cause: err}
	}
	if value.BindingID != target.BindingID || value.ClusterID != p.repository.placement.ClusterID ||
		(value.ProviderUid != "" && target.KnownIdentity != "" && value.ProviderUid != target.KnownIdentity) {
		return value, &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	return value, nil
}

func (p *KCProvider) Observe(ctx context.Context, target biz.ProviderTarget) (biz.ProviderObservation, error) {
	binding, err := p.binding(ctx, target)
	if err != nil {
		return biz.ProviderObservation{}, err
	}
	object, err := p.client.Resource(kcVPCs).Namespace(binding.Namespace).Get(ctx, binding.ProviderName, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		return biz.ProviderObservation{}, nil
	}
	if err != nil {
		return biz.ProviderObservation{}, readFailure(err)
	}
	return inspectVPC(object, binding, target)
}

func inspectVPC(object *unstructured.Unstructured, binding sqlcgen.NetworkProviderBinding, target biz.ProviderTarget) (biz.ProviderObservation, error) {
	labels := object.GetLabels()
	if object.GetName() != binding.ProviderName || object.GetNamespace() != binding.Namespace || object.GetUID() == "" || object.GetResourceVersion() == "" ||
		labels[ownerLabel] != "ani-network-service" || labels[tenantLabel] != target.TenantID || labels[resourceLabel] != target.ResourceID || labels[bindingLabel] != binding.BindingID ||
		(target.KnownIdentity != "" && string(object.GetUID()) != target.KnownIdentity) ||
		(binding.ProviderUid != "" && string(object.GetUID()) != binding.ProviderUid) {
		return biz.ProviderObservation{}, &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	cidr, _, _ := unstructured.NestedString(object.Object, "spec", "cidrBlock")
	ip, _, _ := unstructured.NestedString(object.Object, "spec", "ipVersion")
	allowed, _, _ := unstructured.NestedString(object.Object, "spec", "allowedNamespaces", "from")
	route, _, _ := unstructured.NestedString(object.Object, "spec", "routeTable")
	routes, _, _ := unstructured.NestedSlice(object.Object, "spec", "policyRoutes")
	selector, _, _ := unstructured.NestedMap(object.Object, "spec", "allowedNamespaces", "selector")
	if cidr != target.CIDR || ip != "IPv4" || allowed != "Same" || route != "" || len(routes) > 0 || len(selector) > 0 {
		return biz.ProviderObservation{}, &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	observed, _, _ := unstructured.NestedInt64(object.Object, "status", "observedGeneration")
	router, _, _ := unstructured.NestedString(object.Object, "status", "boundResources", "router")
	conditions, _, _ := unstructured.NestedSlice(object.Object, "status", "conditions")
	good := map[string]bool{}
	for _, raw := range conditions {
		condition, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		kind, _ := condition["type"].(string)
		generation, _, _ := unstructured.NestedInt64(condition, "observedGeneration")
		// The fixed kc helper does not populate condition.observedGeneration;
		// use status.observedGeneration, and reject a contradictory nonzero value.
		good[kind] = condition["status"] == "True" && (generation == 0 || generation == object.GetGeneration())
	}
	subnets, _, _ := unstructured.NestedMap(object.Object, "status", "subnets")
	eips, _, _ := unstructured.NestedMap(object.Object, "status", "eips")
	return biz.ProviderObservation{Exists: true, Identity: string(object.GetUID()), HasDependencies: len(subnets) > 0 || len(eips) > 0,
		Ready: object.GetDeletionTimestamp() == nil && object.GetGeneration() > 0 && observed == object.GetGeneration() && router != "" && good["Valid"] && good["Initialized"] && good["Ready"]}, nil
}

func (p *KCProvider) EnsureVPC(ctx context.Context, target biz.ProviderTarget) (biz.ProviderObservation, error) {
	binding, err := p.binding(ctx, target)
	if err != nil {
		return biz.ProviderObservation{}, err
	}
	if err := p.ensureNamespace(ctx, binding); err != nil {
		return biz.ProviderObservation{}, err
	}
	resource := p.client.Resource(kcVPCs).Namespace(binding.Namespace)
	existing, err := resource.Get(ctx, binding.ProviderName, metav1.GetOptions{})
	if err == nil {
		return inspectVPC(existing, binding, target)
	}
	if !apierrors.IsNotFound(err) {
		return biz.ProviderObservation{}, readFailure(err)
	}
	if target.KnownIdentity != "" || binding.ProviderUid != "" {
		return biz.ProviderObservation{}, &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	object := &unstructured.Unstructured{Object: map[string]any{
		"apiVersion": "networking.kubercloud.com/v1", "kind": "VPC",
		"metadata": map[string]any{"name": binding.ProviderName, "namespace": binding.Namespace, "labels": map[string]any{
			ownerLabel: "ani-network-service", tenantLabel: target.TenantID, resourceLabel: target.ResourceID, bindingLabel: binding.BindingID}},
		"spec": map[string]any{"cidrBlock": target.CIDR, "ipVersion": "IPv4", "allowedNamespaces": map[string]any{"from": "Same"}},
	}}
	created, err := resource.Create(ctx, object, metav1.CreateOptions{FieldManager: "ani-network-service", FieldValidation: "Strict"})
	if apierrors.IsAlreadyExists(err) {
		created, err = resource.Get(ctx, binding.ProviderName, metav1.GetOptions{})
		if err != nil {
			return biz.ProviderObservation{}, &biz.ProviderError{Kind: biz.ProviderUncertain, Cause: err}
		}
	}
	if err != nil {
		return biz.ProviderObservation{}, mutationFailure(err)
	}
	// A malformed success cannot disprove the POST. Preserve pending_create
	// until a later GET supplies an owned object and stable UID.
	value, err := inspectVPC(created, binding, target)
	if err != nil {
		return biz.ProviderObservation{}, &biz.ProviderError{Kind: biz.ProviderUncertain, Cause: err}
	}
	return value, nil
}

func (p *KCProvider) ensureNamespace(ctx context.Context, binding sqlcgen.NetworkProviderBinding) error {
	resource := p.client.Resource(namespaces)
	value, err := resource.Get(ctx, binding.Namespace, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		value, err = resource.Create(ctx, &unstructured.Unstructured{Object: map[string]any{"apiVersion": "v1", "kind": "Namespace",
			"metadata": map[string]any{"name": binding.Namespace, "labels": map[string]any{ownerLabel: "ani-network-service", tenantLabel: binding.TenantID}}}}, metav1.CreateOptions{FieldManager: "ani-network-service"})
		if apierrors.IsAlreadyExists(err) {
			value, err = resource.Get(ctx, binding.Namespace, metav1.GetOptions{})
		}
	}
	// No VPC POST was sent yet; namespace creation can be re-observed safely.
	if err != nil {
		return readFailure(err)
	}
	if value.GetName() != binding.Namespace || value.GetDeletionTimestamp() != nil || value.GetLabels()[tenantLabel] != binding.TenantID || value.GetLabels()[ownerLabel] != "ani-network-service" {
		return &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	return nil
}

func (p *KCProvider) Delete(ctx context.Context, target biz.ProviderTarget) error {
	binding, err := p.binding(ctx, target)
	if err != nil {
		return err
	}
	if target.KnownIdentity == "" {
		return &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	resource := p.client.Resource(kcVPCs).Namespace(binding.Namespace)
	object, err := resource.Get(ctx, binding.ProviderName, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		return nil
	}
	if err != nil {
		return readFailure(err)
	}
	observed, err := inspectVPC(object, binding, target)
	if err != nil {
		return err
	}
	if observed.HasDependencies {
		return &biz.ProviderError{Kind: biz.ProviderInUse}
	}
	// A status map can lag. Read every namespace because an unexpected external
	// subnet may still reference this VPC. Never cascade or remove finalizers.
	continuation := ""
	for {
		children, err := p.client.Resource(kcSubnets).List(ctx, metav1.ListOptions{Limit: 500, Continue: continuation})
		if err != nil {
			return readFailure(err)
		}
		for _, child := range children.Items {
			gateway, _, _ := unstructured.NestedString(child.Object, "spec", "gateway")
			if gateway == binding.Namespace+"/"+binding.ProviderName {
				return &biz.ProviderError{Kind: biz.ProviderInUse}
			}
		}
		continuation = children.GetContinue()
		if continuation == "" {
			break
		}
	}
	uid := types.UID(target.KnownIdentity)
	revision := object.GetResourceVersion()
	orphan := metav1.DeletePropagationOrphan
	err = resource.Delete(ctx, binding.ProviderName, metav1.DeleteOptions{Preconditions: &metav1.Preconditions{UID: &uid, ResourceVersion: &revision}, PropagationPolicy: &orphan})
	if apierrors.IsNotFound(err) {
		return nil
	}
	if err != nil {
		return mutationFailure(err)
	}
	return nil
}

func readFailure(err error) error { return &biz.ProviderError{Kind: biz.ProviderTemporary, Cause: err} }
func mutationFailure(err error) error {
	kind := biz.ProviderUncertain
	switch {
	case apierrors.IsConflict(err):
		kind = biz.ProviderConflict
	case apierrors.IsInvalid(err) || apierrors.IsBadRequest(err):
		kind = biz.ProviderReject
	case apierrors.IsForbidden(err) || apierrors.IsUnauthorized(err) || apierrors.IsTooManyRequests(err):
		kind = biz.ProviderTemporary
	default:
		var status apierrors.APIStatus
		if errors.As(err, &status) && status.Status().Code == http.StatusRequestEntityTooLarge {
			kind = biz.ProviderReject
		}
	}
	return &biz.ProviderError{Kind: kind, Cause: err}
}
