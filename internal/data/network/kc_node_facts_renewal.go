package data

import (
	"encoding/json"
	"reflect"
	"time"

	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

// A successful collector heartbeat advances timestamps without changing the
// sampled device facts. It must not repeatedly invalidate a complete audit that
// still has fresh evidence. This does not renew that audit's original timestamps;
// the normal periodic/critical collection must read the new document itself.
func unchangedNodeFactsRenewal(before, after *unstructured.Unstructured, now time.Time) bool {
	old, oldAt, ok := nodeFactsWithoutRenewal(before, now)
	if !ok {
		return false
	}
	next, nextAt, ok := nodeFactsWithoutRenewal(after, now)
	return ok && !nextAt.Before(oldAt) && reflect.DeepEqual(old.Object, next.Object)
}

func nodeFactsWithoutRenewal(object *unstructured.Unstructured, now time.Time) (*unstructured.Unstructured, time.Time, bool) {
	if object == nil || object.GetAPIVersion() != "v1" || object.GetKind() != "ConfigMap" || object.GetNamespace() != kcSystemNamespace || object.GetUID() == "" || object.GetDeletionTimestamp() != nil || object.GetLabels()[ownerLabel] != factsOwner {
		return nil, time.Time{}, false
	}
	body := []byte(crString(object, "data", "facts.json"))
	if len(body) == 0 || len(body) > 4<<20 {
		return nil, time.Time{}, false
	}
	var doc NodeFactsDocument
	if json.Unmarshal(body, &doc) != nil || doc.Version != 1 || doc.NodeName == "" || doc.NodeUID == "" || doc.NodeUID != object.GetLabels()[factsNodeLabel] || len(doc.Interfaces) == 0 || doc.CollectedAt.IsZero() || doc.CollectedAt.After(now) || now.Sub(doc.CollectedAt) > time.Minute {
		return nil, time.Time{}, false
	}
	seen := map[string]bool{}
	for _, iface := range doc.Interfaces {
		if iface.Name == "" || seen[iface.Name] || iface.NodeName != doc.NodeName || iface.NodeUID != doc.NodeUID || (!iface.ObservedAt.IsZero() && !iface.ObservedAt.Equal(doc.CollectedAt)) {
			return nil, time.Time{}, false
		}
		seen[iface.Name] = true
	}
	// Compare the raw JSON after removing only known time fields, so unknown
	// future fields and additional ConfigMap data still invalidate the audit.
	var raw map[string]any
	if json.Unmarshal(body, &raw) != nil {
		return nil, time.Time{}, false
	}
	interfaces, ok := raw["interfaces"].([]any)
	if !ok || len(interfaces) != len(doc.Interfaces) {
		return nil, time.Time{}, false
	}
	for _, item := range interfaces {
		iface, ok := item.(map[string]any)
		if !ok {
			return nil, time.Time{}, false
		}
		delete(iface, "ObservedAt")
	}
	delete(raw, "collected_at")
	stable, err := json.Marshal(raw)
	if err != nil {
		return nil, time.Time{}, false
	}
	copy := object.DeepCopy()
	unstructured.RemoveNestedField(copy.Object, "metadata", "resourceVersion")
	unstructured.RemoveNestedField(copy.Object, "metadata", "managedFields")
	if unstructured.SetNestedField(copy.Object, string(stable), "data", "facts.json") != nil {
		return nil, time.Time{}, false
	}
	return copy, doc.CollectedAt, true
}
