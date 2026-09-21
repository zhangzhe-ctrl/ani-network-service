package data_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/data/network"
	"k8s.io/client-go/rest"
)

func TestConfirmedProviderRejectionFailsCreationButKeepsDeletionRecoverable(t *testing.T) {
	repository, _ := database(t)
	n := newNetwork(t, repository, time.Minute)
	api := &controlledKC{}
	var rejected atomic.Int32
	host := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && strings.HasSuffix(r.URL.Path, "/vpcs") {
			rejected.Add(1)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(422)
			_, _ = w.Write([]byte(`{"apiVersion":"v1","kind":"Status","status":"Failure","reason":"Invalid","code":422}`))
			return
		}
		api.ServeHTTP(w, r)
	}))
	defer host.Close()
	provider, err := data.NewKCProvider(repository, &rest.Config{Host: host.URL})
	if err != nil {
		t.Fatal(err)
	}
	worker, err := biz.NewWorker(repository, provider, uuid.NewString(), fastPolicy())
	if err != nil {
		t.Fatal(err)
	}
	v := create(t, n, "rejected")
	runStep(t, worker)
	ctx := context.Background()
	failed, err := n.GetVPC(ctx, v.TenantID, v.ID)
	if err != nil || failed.State != biz.Failed || failed.Reason != biz.ProviderRejected {
		t.Fatalf("definite rejection: %+v %v", failed, err)
	}
	op, err := n.GetOperation(ctx, v.TenantID, v.LastOperationID)
	if err != nil || op.State != biz.OpFailed {
		t.Fatalf("failed operation: %+v %v", op, err)
	}
	time.Sleep(15 * time.Millisecond)
	runStep(t, worker)
	stillFailed, err := n.GetVPC(ctx, v.TenantID, v.ID)
	if err != nil || stillFailed.Reason != biz.ProviderRejected {
		t.Fatalf("continuous observation erased creation failure reason: %+v %v", stillFailed, err)
	}
	deleting, err := n.DeleteVPC(ctx, v.TenantID, v.ID)
	if err != nil {
		t.Fatal(err)
	}
	runStep(t, worker)
	final, err := n.GetVPC(ctx, v.TenantID, v.ID)
	if err != nil || final.State != biz.Deleted || final.LastOperationID != deleting.LastOperationID || rejected.Load() != 1 {
		t.Fatalf("failed create cleanup: %+v %v", final, err)
	}
}

func TestActualAdapterBlocksWrongOwnerChangedUIDAndUnexpectedChildren(t *testing.T) {
	for _, fault := range []string{"foreign-owner", "changed-uid", "status-children", "unreported-children"} {
		t.Run(fault, func(t *testing.T) {
			repository, _ := database(t)
			n := newNetwork(t, repository, time.Minute)
			api := &controlledKC{}
			var childReference atomic.Value
			childReference.Store("")
			host := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if ref := childReference.Load().(string); ref != "" && strings.HasSuffix(r.URL.Path, "/subnets") {
					w.Header().Set("Content-Type", "application/json")
					_, _ = w.Write([]byte(`{"apiVersion":"networking.kubercloud.com/v1","kind":"SubnetList","items":[{"metadata":{"name":"unexpected"},"spec":{"gateway":"` + ref + `"}}]}`))
					return
				}
				api.ServeHTTP(w, r)
			}))
			defer host.Close()
			provider, err := data.NewKCProvider(repository, &rest.Config{Host: host.URL})
			if err != nil {
				t.Fatal(err)
			}
			worker, err := biz.NewWorker(repository, provider, uuid.NewString(), fastPolicy())
			if err != nil {
				t.Fatal(err)
			}
			v := create(t, n, fault)
			runStep(t, worker)
			api.mu.Lock()
			metadata := api.object["metadata"].(map[string]any)
			switch fault {
			case "foreign-owner":
				metadata["labels"].(map[string]any)["network.ani.io/managed-by"] = "external"
			case "changed-uid":
				metadata["uid"] = "replacement-uid"
			case "status-children":
				api.object["status"].(map[string]any)["subnets"] = map[string]any{"foreign/child": "10.42.1.0/24"}
			case "unreported-children":
				childReference.Store(metadata["namespace"].(string) + "/" + metadata["name"].(string))
			}
			api.mu.Unlock()
			ctx := context.Background()
			if fault == "foreign-owner" || fault == "changed-uid" {
				time.Sleep(10 * time.Millisecond)
				runStep(t, worker)
				conflicted, err := n.GetVPC(ctx, v.TenantID, v.ID)
				if err != nil || conflicted.State != biz.Degraded {
					t.Fatalf("known ownership conflict kept available: %+v %v", conflicted, err)
				}
			}
			deleting, err := n.DeleteVPC(ctx, v.TenantID, v.ID)
			if err != nil {
				t.Fatal(err)
			}
			runStep(t, worker)
			op, err := n.GetOperation(ctx, v.TenantID, deleting.LastOperationID)
			reason := biz.ProviderOwnership
			if strings.Contains(fault, "children") {
				reason = biz.ResourceInUse
			}
			if err != nil || op.State != biz.Blocked || op.Reason != reason {
				t.Fatalf("unsafe deletion not blocked: %+v %v", op, err)
			}
			api.mu.Lock()
			defer api.mu.Unlock()
			if api.deletes != 0 || api.object == nil {
				t.Fatal("unsafe object was deleted")
			}
		})
	}
}

func TestProviderOutageAndStaleGenerationCannotBecomeAvailable(t *testing.T) {
	repository, _ := database(t)
	n := newNetwork(t, repository, 30*time.Millisecond)
	api := &controlledKC{}
	var outage atomic.Bool
	host := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if outage.Load() {
			http.Error(w, "offline", 503)
			return
		}
		api.ServeHTTP(w, r)
	}))
	defer host.Close()
	provider, err := data.NewKCProvider(repository, &rest.Config{Host: host.URL})
	if err != nil {
		t.Fatal(err)
	}
	worker, err := biz.NewWorker(repository, provider, uuid.NewString(), fastPolicy())
	if err != nil {
		t.Fatal(err)
	}
	v := create(t, n, "outage")
	runStep(t, worker)
	outage.Store(true)
	time.Sleep(45 * time.Millisecond)
	runStep(t, worker)
	ctx := context.Background()
	got, err := n.GetVPC(ctx, v.TenantID, v.ID)
	if err != nil || got.State != biz.Degraded || got.Reason != biz.ProviderUnavailable {
		t.Fatalf("outage masked: %+v %v", got, err)
	}
	op, err := n.GetOperation(ctx, v.TenantID, v.LastOperationID)
	if err != nil || op.State != biz.Succeeded {
		t.Fatalf("outage rewrote history: %+v %v", op, err)
	}
	outage.Store(false)
	api.mu.Lock()
	api.object["status"].(map[string]any)["observedGeneration"] = float64(0)
	api.mu.Unlock()
	time.Sleep(10 * time.Millisecond)
	runStep(t, worker)
	got, err = n.GetVPC(ctx, v.TenantID, v.ID)
	if err != nil || got.State != biz.Degraded {
		t.Fatalf("stale generation became ready: %+v %v", got, err)
	}
	api.mu.Lock()
	api.object["status"].(map[string]any)["observedGeneration"] = float64(1)
	api.mu.Unlock()
	time.Sleep(10 * time.Millisecond)
	runStep(t, worker)
	got, err = n.GetVPC(ctx, v.TenantID, v.ID)
	if err != nil || got.State != biz.Available {
		t.Fatalf("observation did not recover: %+v %v", got, err)
	}
}
