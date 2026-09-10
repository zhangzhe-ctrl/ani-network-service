package data

import (
	"context"
	"encoding/json"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data/sqlcgen"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sort"
	"strconv"
	"strings"
)

const attachmentLabel = "network.ani.io/attachment-id"
const instanceLabel = "network.ani.io/instance-id"
const submissionLabel = "network.ani.io/submission-id"
const generationLabel = "network.ani.io/generation"
const subnetAnnotation = "networking.kubercloud.com/subnet"

var pods = schema.GroupVersionResource{Version: "v1", Resource: "pods"}

type attachmentRelation struct{ Kind, Namespace, Name, UID, OwnerUID string }

func (p *KCProvider) listAll(ctx context.Context, resource schema.GroupVersionResource) ([]unstructured.Unstructured, error) {
	var values []unstructured.Unstructured
	next := ""
	for {
		page, e := p.client.Resource(resource).List(ctx, metav1.ListOptions{Limit: 500, Continue: next})
		if e != nil {
			return nil, readFailure(e)
		}
		values = append(values, page.Items...)
		next = page.GetContinue()
		if next == "" {
			return values, nil
		}
	}
}
func kcRef(value, namespace string) string {
	if value != "" && !strings.Contains(value, "/") {
		return namespace + "/" + value
	}
	return value
}
func relationKey(kind, ns, name string) string { return kind + "/" + ns + "/" + name }
func ownerUID(o unstructured.Unstructured, kind string, ids map[string]bool) (string, bool) {
	for _, r := range o.GetOwnerReferences() {
		if r.Kind == kind && ids[string(r.UID)] && r.APIVersion == map[string]string{"Pod": "v1", "VNic": "networking.kubercloud.com/v1"}[kind] {
			return string(r.UID), true
		}
	}
	return "", false
}
func (p *KCProvider) ObserveAttachment(ctx context.Context, w biz.AttachmentWork) (biz.AttachmentObservation, error) {
	a, plan := w.Attachment, w.Plan
	conflict := func() (biz.AttachmentObservation, error) {
		return biz.AttachmentObservation{}, &biz.ProviderError{Kind: biz.ProviderConflict}
	}
	b, e := p.repository.queries.GetBinding(ctx, sqlcgen.GetBindingParams{TenantID: a.TenantID, ResourceID: a.SubnetID})
	if e != nil {
		return biz.AttachmentObservation{}, readFailure(e)
	}
	if b.ClusterID != a.ClusterID || b.ClusterID != p.repository.placement.ClusterID || b.Namespace != a.Namespace || b.BindingID+":"+b.ProviderUid != a.BindingRevision || plan.PrimaryNetworkRef != b.Namespace+"/"+b.ProviderName {
		return conflict()
	}
	tracked := map[string]attachmentRelation{}
	var prior []attachmentRelation
	if e = json.Unmarshal(w.Relations, &prior); e != nil {
		return biz.AttachmentObservation{}, readFailure(e)
	}
	podUIDs := map[string]bool{}
	if a.PodUID != "" {
		podUIDs[a.PodUID] = true
	}
	for _, id := range w.ConsumerPodUIDs {
		podUIDs[id] = true
	}
	vnicUIDs := map[string]bool{}
	vnicNames := map[string]string{}
	for _, r := range prior {
		tracked[relationKey(r.Kind, r.Namespace, r.Name)] = r
		if r.Kind == "VNic" {
			vnicUIDs[r.UID] = true
			vnicNames[r.Namespace+"/"+r.Name] = r.UID
		}
	}
	allPods, e := p.listAll(ctx, pods)
	if e != nil {
		return biz.AttachmentObservation{}, e
	}
	result := biz.AttachmentObservation{}
	var pod *unstructured.Unstructured
	for _, o := range allPods {
		labels := o.GetLabels()
		candidate := labels[attachmentLabel] == a.ID || podUIDs[string(o.GetUID())] || (a.PodName != "" && o.GetNamespace() == a.Namespace && o.GetName() == a.PodName)
		if !candidate {
			continue
		}
		if pod != nil || o.GetKind() != "Pod" || o.GetAPIVersion() != "v1" || o.GetNamespace() != a.Namespace || o.GetUID() == "" || o.GetResourceVersion() == "" || labels[tenantLabel] != a.TenantID || labels[instanceLabel] != a.InstanceID || labels[attachmentLabel] != a.ID || labels[submissionLabel] != a.SubmissionID || labels[generationLabel] != strconv.FormatInt(a.Generation, 10) || o.GetAnnotations()[subnetAnnotation] != plan.PrimaryNetworkRef || (a.PodUID != "" && a.PodUID != string(o.GetUID())) {
			return conflict()
		}
		for key, value := range o.GetAnnotations() {
			if value != "" && (key == "k8s.v1.cni.cncf.io/networks" || strings.HasPrefix(key, "ovn.kubernetes.io/") || strings.HasSuffix(key, ".networking.kubercloud.com/subnet") || strings.HasSuffix(key, ".networking.kubercloud.com/vnic") || strings.HasSuffix(key, ".networking.kubercloud.com/vnicip")) {
				return conflict()
			}
		}
		copy := o
		pod = &copy
		result.Exists = true
		result.PodName = o.GetName()
		result.PodUID = string(o.GetUID())
		podUIDs[result.PodUID] = true
	}
	vnics, e := p.listAll(ctx, schema.GroupVersionResource{Group: kcVPCs.Group, Version: kcVPCs.Version, Resource: "vnics"})
	if e != nil {
		return result, e
	}
	liveVNics := map[string]string{}
	for _, o := range vnics {
		key := relationKey("VNic", o.GetNamespace(), o.GetName())
		old, seen := tracked[key]
		owner, owned := ownerUID(o, "Pod", podUIDs)
		podAnnotation := false
		if result.PodName != "" {
			_, podAnnotation = o.GetAnnotations()["pod.networking.kubercloud.com/"+result.PodName]
		}
		if a.PodName != "" {
			_, known := o.GetAnnotations()["pod.networking.kubercloud.com/"+a.PodName]
			podAnnotation = podAnnotation || known
		}
		if !owned && !seen && !podAnnotation {
			continue
		}
		subnet, _, _ := unstructured.NestedString(o.Object, "spec", "subnet")
		kind, _, _ := unstructured.NestedString(o.Object, "spec", "type")
		if !owned || o.GetKind() != "VNic" || o.GetAPIVersion() != "networking.kubercloud.com/v1" || o.GetNamespace() != a.Namespace || o.GetUID() == "" || kind != "VETH" || kcRef(subnet, o.GetNamespace()) != plan.PrimaryNetworkRef || (seen && old.UID != string(o.GetUID())) {
			return conflict()
		}
		uid := string(o.GetUID())
		tracked[key] = attachmentRelation{"VNic", o.GetNamespace(), o.GetName(), uid, owner}
		vnicUIDs[uid] = true
		vnicNames[o.GetNamespace()+"/"+o.GetName()] = uid
		liveVNics[o.GetNamespace()+"/"+o.GetName()] = uid
		result.HasDependencies = true
	}
	ips, e := p.listAll(ctx, schema.GroupVersionResource{Group: kcVPCs.Group, Version: kcVPCs.Version, Resource: "vnicips"})
	if e != nil {
		return result, e
	}
	liveIPs := map[string]string{}
	for _, o := range ips {
		key := relationKey("VNicIP", o.GetNamespace(), o.GetName())
		old, seen := tracked[key]
		owner, owned := ownerUID(o, "VNic", vnicUIDs)
		ref, _, _ := unstructured.NestedString(o.Object, "spec", "vNic")
		statusRef, _, _ := unstructured.NestedString(o.Object, "status", "vNic")
		related := vnicNames[kcRef(ref, o.GetNamespace())] != "" || vnicNames[kcRef(statusRef, o.GetNamespace())] != ""
		if !owned && !seen && !related {
			continue
		}
		subnet, _, _ := unstructured.NestedString(o.Object, "spec", "subnet")
		if !owned || o.GetKind() != "VNicIP" || o.GetAPIVersion() != "networking.kubercloud.com/v1" || o.GetNamespace() != a.Namespace || o.GetUID() == "" || kcRef(subnet, o.GetNamespace()) != plan.PrimaryNetworkRef || (seen && old.UID != string(o.GetUID())) || (ref != "" && vnicNames[kcRef(ref, o.GetNamespace())] != owner) || (statusRef != "" && vnicNames[kcRef(statusRef, o.GetNamespace())] != owner) {
			return conflict()
		}
		tracked[key] = attachmentRelation{"VNicIP", o.GetNamespace(), o.GetName(), string(o.GetUID()), owner}
		liveIPs[o.GetNamespace()+"/"+o.GetName()] = string(o.GetUID())
		result.HasDependencies = true
	}
	if pod != nil {
		annotations := pod.GetAnnotations()
		if value := annotations["networking.kubercloud.com/vnic"]; value != "" && liveVNics[kcRef(value, a.Namespace)] == "" {
			return conflict()
		}
		if value := annotations["networking.kubercloud.com/vnicip"]; value != "" && liveIPs[kcRef(value, a.Namespace)] == "" {
			return conflict()
		}
	}
	// Keep every witnessed UID after absence: a later same-name replacement or
	// an orphaned IP referring to a deleted VNic must still be attributable.
	keys := make([]string, 0, len(tracked))
	for k := range tracked {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	relations := make([]attachmentRelation, 0, len(keys))
	for _, k := range keys {
		relations = append(relations, tracked[k])
	}
	result.Relations, _ = json.Marshal(relations)
	return result, nil
}
