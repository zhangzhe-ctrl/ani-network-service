package data

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

func TestNET05ANodeFactsRenewalsKeepAuditWhileChangesInvalidate(t *testing.T) {
	now := time.Now().UTC()
	document := func(at time.Time) map[string]any {
		doc := NodeFactsDocument{Version: 1, NodeName: "node-a", NodeUID: "node-uid", CollectedAt: at,
			Interfaces: []biz.NodeInterface{{NodeName: "node-a", NodeUID: "node-uid", Name: "ens35", Kind: "device", MAC: "02:00:00:00:00:01", ObservedAt: at, KCBridgeReady: true}}}
		body, _ := json.Marshal(doc)
		var value map[string]any
		_ = json.Unmarshal(body, &value)
		return value
	}
	object := func(at time.Time, rv string) *unstructured.Unstructured {
		body, _ := json.Marshal(document(at))
		return &unstructured.Unstructured{Object: map[string]any{"apiVersion": "v1", "kind": "ConfigMap",
			"metadata": map[string]any{"name": "facts-node-a", "namespace": kcSystemNamespace, "uid": "facts-uid", "resourceVersion": rv,
				"labels": map[string]any{ownerLabel: factsOwner, factsNodeLabel: "node-uid"}}, "data": map[string]any{"facts.json": string(body)}}}
	}
	changeDocument := func(o *unstructured.Unstructured, change func(map[string]any)) {
		var v map[string]any
		_ = json.Unmarshal([]byte(crString(o, "data", "facts.json")), &v)
		change(v)
		body, _ := json.Marshal(v)
		_ = unstructured.SetNestedField(o.Object, string(body), "data", "facts.json")
	}
	for _, tc := range []struct {
		name   string
		change func(*unstructured.Unstructured)
		keep   bool
	}{
		{"fresh_renewal", func(*unstructured.Unstructured) {}, true},
		{"MAC_replacement", func(o *unstructured.Unstructured) {
			changeDocument(o, func(v map[string]any) { v["interfaces"].([]any)[0].(map[string]any)["MAC"] = "02:ff:ff:ff:ff:ff" })
		}, false},
		{"bridge_changed", func(o *unstructured.Unstructured) {
			changeDocument(o, func(v map[string]any) { v["interfaces"].([]any)[0].(map[string]any)["KCBridgeReady"] = false })
		}, false},
		{"unknown_document_field_changed", func(o *unstructured.Unstructured) {
			changeDocument(o, func(v map[string]any) { v["future_contract"] = "changed" })
		}, false},
		{"unknown_interface_field_changed", func(o *unstructured.Unstructured) {
			changeDocument(o, func(v map[string]any) { v["interfaces"].([]any)[0].(map[string]any)["FutureContract"] = "changed" })
		}, false},
		{"UID_replacement", func(o *unstructured.Unstructured) { o.SetUID("replacement") }, false},
		{"owner_changed", func(o *unstructured.Unstructured) {
			o.SetLabels(map[string]string{ownerLabel: "foreign", factsNodeLabel: "node-uid"})
		}, false},
		{"timestamp_regression", func(o *unstructured.Unstructured) { *o = *object(now.Add(-3*time.Second), "3") }, false},
		{"future_timestamp", func(o *unstructured.Unstructured) { *o = *object(now.Add(time.Minute), "3") }, false},
		{"stale_timestamp", func(o *unstructured.Unstructured) { *o = *object(now.Add(-2*time.Minute), "3") }, false},
		{"malformed_document", func(o *unstructured.Unstructured) {
			_ = unstructured.SetNestedField(o.Object, "{", "data", "facts.json")
		}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			before, after := object(now.Add(-2*time.Second), "1"), object(now.Add(-time.Second), "2")
			tc.change(after)
			oldBody, _ := json.Marshal(before.Object)
			newBody, _ := json.Marshal(after.Object)
			o := &KCObservation{options: ObservationOptions{QueueCapacity: 16}, pending: map[string]struct{}{}, changes: map[string]uint64{}}
			view := &auditView{collected: now.Add(-3 * time.Second)}
			o.view = view
			o.changed(before, after)
			if kept := o.valid(view, []string{"node-facts"}); kept != tc.keep {
				t.Fatalf("prior audit validity=%v want %v", kept, tc.keep)
			}
			oldAfter, _ := json.Marshal(before.Object)
			newAfter, _ := json.Marshal(after.Object)
			if string(oldBody) != string(oldAfter) || string(newBody) != string(newAfter) || !view.collected.Equal(now.Add(-3*time.Second)) {
				t.Fatal("notification mutated source facts or renewed the old audit time")
			}
		})
	}
	t.Run("fresh_renewal_cannot_revive_stale_source", func(t *testing.T) {
		o := &KCObservation{options: ObservationOptions{QueueCapacity: 16}, pending: map[string]struct{}{}, changes: map[string]uint64{}}
		view := &auditView{collected: now.Add(-2 * time.Minute)}
		o.changed(object(now.Add(-2*time.Minute), "1"), object(now.Add(-time.Second), "2"))
		if o.valid(view, []string{"node-facts"}) {
			t.Fatal("fresh renewal revived an expired source without a new audit")
		}
	})
}
