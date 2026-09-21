package data

import (
	"reflect"
	"testing"
	"time"

	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
)

func TestAuditCandidateHashIgnoresListOrderButPreservesFacts(t *testing.T) {
	object := func(name, uid string) unstructured.Unstructured {
		return unstructured.Unstructured{Object: map[string]any{
			"apiVersion": "v1", "kind": "Pod",
			"metadata": map[string]any{"namespace": "tenant", "name": name, "uid": uid, "resourceVersion": "12"},
			"status":   map[string]any{"podIP": "10.0.0.2"},
		}}
	}
	a, b := object("a", "uid-a"), object("b", "uid-b")
	first := map[schema.GroupVersionResource][]unstructured.Unstructured{pods: {a, b}}
	reordered := map[schema.GroupVersionResource][]unstructured.Unstructured{pods: {b, a}}
	hash := contentHash(candidatesForHash(first))
	secondHash := contentHash(candidatesForHash(reordered))
	if hash != secondHash {
		t.Error("same complete object set changed its evidence hash after List order changed")
	}
	if !reflect.DeepEqual(first[pods], []unstructured.Unstructured{a, b}) || !reflect.DeepEqual(reordered[pods], []unstructured.Unstructured{b, a}) {
		t.Fatal("hashing reordered an input slice owned by the observation view")
	}
	now := time.Now()
	proof := biz.ObservationProof{CollectedAt: now.Add(-time.Second), CoveredGeneration: 1, Hash: secondHash}
	if !proof.Covers(biz.ObservationRequirement{RequestedGeneration: 1, AppliedAt: now, Hash: hash}) {
		t.Error("unchanged cached evidence cannot cover its previously applied facts")
	}
	for _, field := range []string{"uid", "resourceVersion", "podIP"} {
		t.Run(field, func(t *testing.T) {
			changed := a.DeepCopy()
			if field == "podIP" {
				changed.Object["status"].(map[string]any)[field] = "10.0.0.99"
			} else {
				changed.Object["metadata"].(map[string]any)[field] = "replacement"
			}
			if contentHash(candidatesForHash(map[schema.GroupVersionResource][]unstructured.Unstructured{pods: {b, *changed}})) == hash {
				t.Fatal("changed identity or fact kept the old evidence hash")
			}
		})
	}
}
