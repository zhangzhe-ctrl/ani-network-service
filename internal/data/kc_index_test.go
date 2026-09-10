package data

import (
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/client-go/tools/cache"
	"testing"
)

func TestNET05ARelationshipOldNewTombstoneAndUnrelatedEvents(t *testing.T) {
	o := &KCObservation{options: ObservationOptions{QueueCapacity: 16}, pending: map[string]struct{}{}, changes: map[string]uint64{}}
	old := &unstructured.Unstructured{Object: map[string]any{"kind": "Pod", "apiVersion": "v1", "metadata": map[string]any{"namespace": "ns", "name": "pod", "uid": "old", "labels": map[string]any{attachmentLabel: "a"}}}}
	next := old.DeepCopy()
	next.SetUID("new")
	next.SetLabels(map[string]string{attachmentLabel: "b"})
	v := &auditView{sequence: 0, epoch: 0}
	o.changed(old, next)
	for _, key := range []string{"attachment:a", "attachment:b", "uid:old", "uid:new"} {
		if _, ok := o.pending[key]; !ok {
			t.Fatalf("lost old/new side: %s", key)
		}
	}
	if o.valid(v, []string{"attachment:a"}) {
		t.Fatal("old LIST remained valid across related Watch")
	}
	if !o.valid(v, []string{"attachment:unrelated"}) {
		t.Fatal("unrelated event invalidated entire scope")
	}
	clear(o.pending)
	o.changed(cache.DeletedFinalStateUnknown{Key: "ns/pod", Obj: old}, nil)
	if _, ok := o.pending["uid:old"]; !ok {
		t.Fatal("tombstone identity lost")
	}
	before := o.sequence
	o.changed(next, next.DeepCopy())
	if o.sequence != before {
		t.Fatal("duplicate/resync became new fact")
	}
}

func TestNET05ASourceBoundaryInvalidatesOldAuditWithoutOrderingRV(t *testing.T) {
	o := &KCObservation{options: ObservationOptions{QueueCapacity: 16}, pending: map[string]struct{}{}, changes: map[string]uint64{}}
	old := &auditView{epoch: 0, sequence: 0}
	if !o.valid(old, []string{"uid:x"}) {
		t.Fatal("initial view unexpectedly invalid")
	}
	o.sourceBoundary()
	if o.valid(old, []string{"uid:x"}) || !o.overflow {
		t.Fatal("source reconnect preserved old audit proof")
	}
	current := &auditView{epoch: o.epoch, sequence: o.sequence}
	if !o.valid(current, []string{"uid:x"}) {
		t.Fatal("new complete scope cannot recover")
	}
}
