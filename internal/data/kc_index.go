package data

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strings"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/tools/cache"
)

var observationGVRs = []schema.GroupVersionResource{kcVPCs, kcSubnets, pods,
	{Group: kcVPCs.Group, Version: "v1", Resource: "vnics"},
	{Group: kcVPCs.Group, Version: "v1", Resource: "vnicips"},
	{Group: kcVPCs.Group, Version: "v1", Resource: "eips"},
}

const relationshipIndex = "network-relationship"

// The same keys index Watch and independent complete audit views. No label
// selector filters the collection: unlabeled/orphaned dependencies remain visible.
func relationshipKeys(value any) ([]string, error) {
	o, ok := value.(*unstructured.Unstructured)
	if !ok {
		return nil, nil
	}
	keys := []string{"object:" + o.GetKind() + "/" + o.GetNamespace() + "/" + o.GetName(), "uid:" + string(o.GetUID())}
	if a := o.GetLabels()[attachmentLabel]; a != "" {
		keys = append(keys, "attachment:"+a)
	}
	for _, r := range o.GetOwnerReferences() {
		keys = append(keys, "uid:"+string(r.UID))
	}
	for _, field := range []string{"subnet", "gateway", "vNic"} {
		for _, section := range []string{"spec", "status"} {
			v, _, _ := unstructured.NestedString(o.Object, section, field)
			if v != "" {
				keys = append(keys, field+":"+kcRef(v, o.GetNamespace()))
			}
		}
	}
	if ref := o.GetAnnotations()[subnetAnnotation]; ref != "" {
		keys = append(keys, "subnet:"+kcRef(ref, o.GetNamespace()))
	}
	for k := range o.GetAnnotations() {
		if name, ok := strings.CutPrefix(k, "pod.networking.kubercloud.com/"); ok {
			keys = append(keys, "podname:"+o.GetNamespace()+"/"+name)
		}
	}
	switch o.GetKind() {
	case "VPC":
		keys = append(keys, "gateway:"+o.GetNamespace()+"/"+o.GetName())
	case "Subnet":
		keys = append(keys, "subnet:"+o.GetNamespace()+"/"+o.GetName())
	case "EIP":
		ref, _, _ := unstructured.NestedString(o.Object, "spec", "subnet")
		if ref != "" {
			keys = append(keys, "eip-subnet:"+kcRef(ref, o.GetNamespace()))
		}
	case "VNic":
		keys = append(keys, "vNic:"+o.GetNamespace()+"/"+o.GetName())
	case "Pod":
		keys = append(keys, "podname:"+o.GetNamespace()+"/"+o.GetName())
	}
	return keys, nil
}
func indexedObjects(index cache.Indexer, keys []string) []unstructured.Unstructured {
	seen := map[string]*unstructured.Unstructured{}
	for _, key := range keys {
		values, _ := index.ByIndex(relationshipIndex, key)
		for _, raw := range values {
			o := raw.(*unstructured.Unstructured)
			seen[o.GetNamespace()+"/"+o.GetName()] = o
		}
	}
	names := make([]string, 0, len(seen))
	for k := range seen {
		names = append(names, k)
	}
	sort.Strings(names)
	result := make([]unstructured.Unstructured, 0, len(names))
	for _, k := range names {
		result = append(result, *seen[k])
	}
	return result
}
func contentHash(value any) string {
	b, _ := json.Marshal(value)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
