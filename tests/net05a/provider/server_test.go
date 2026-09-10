package provider

import (
	"context"
	"fmt"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/rest"
	"net/http/httptest"
	"testing"
)

func TestIndependentPaginatedSnapshotsKeepTheirRevisionAndContents(t *testing.T) {
	s := New()
	for i := 0; i < 6; i++ {
		s.Change("pods", map[string]any{"apiVersion": "v1", "kind": "Pod", "metadata": map[string]any{"namespace": "ns", "name": fmt.Sprint("p", i), "uid": fmt.Sprint("uid", i)}}, false)
	}
	h := httptest.NewServer(s)
	defer h.Close()
	client, e := dynamic.NewForConfig(&rest.Config{Host: h.URL})
	if e != nil {
		t.Fatal(e)
	}
	resource := client.Resource(schema.GroupVersionResource{Version: "v1", Resource: "pods"})
	ctx := context.Background()
	a, e := resource.List(ctx, metav1.ListOptions{Limit: 3})
	if e != nil {
		t.Fatal(e)
	}
	b, e := resource.List(ctx, metav1.ListOptions{Limit: 3})
	if e != nil {
		t.Fatal(e)
	}
	if a.GetContinue() == b.GetContinue() {
		t.Fatal("two replicas shared an opaque continuation")
	}
	s.Change("pods", map[string]any{"apiVersion": "v1", "kind": "Pod", "metadata": map[string]any{"namespace": "ns", "name": "after", "uid": "after"}}, false)
	for _, first := range []struct{ token, rv string }{{a.GetContinue(), a.GetResourceVersion()}, {b.GetContinue(), b.GetResourceVersion()}} {
		next, e := resource.List(ctx, metav1.ListOptions{Limit: 3, Continue: first.token})
		if e != nil {
			t.Fatal(e)
		}
		if next.GetResourceVersion() != first.rv || len(next.Items) != 3 || next.GetContinue() != "" {
			t.Fatal("pagination changed its original collection")
		}
	}
}
