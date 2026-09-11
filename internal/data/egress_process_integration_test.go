package data_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	controlled "github.com/zhangzhe-ctrl/ani-network-service/tests/net05a/provider"
	"github.com/zhangzhe-ctrl/ani-network-service/tests/testenv"
)

func TestEgressServiceProcessesRecoverLostCreateDeleteAndTombstone(t *testing.T) {
	if os.Getenv("NETWORK_TEST_ADMIN_DSN") == "" {
		t.Skip("requires isolated PostgreSQL")
	}
	root, err := filepath.Abs("../..")
	if err != nil {
		t.Fatal(err)
	}
	binary := filepath.Join(t.TempDir(), "network-egress")
	build := exec.Command("go", "build", "-race", "-trimpath", "-o", binary, "./cmd/ani-network-service")
	build.Dir = root
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build egress recovery process: %v\n%s", err, output)
	}
	createReached, createRelease := make(chan struct{}), make(chan struct{})
	deleteReached, deleteRelease := make(chan struct{}), make(chan struct{})
	defer close(createRelease)
	defer close(deleteRelease)
	var sawCreate, sawDelete atomic.Bool
	var saved map[string]any
	intercept := func(w http.ResponseWriter, r *http.Request, api *controlled.Server) bool {
		create := r.Method == "POST" && strings.HasSuffix(r.URL.Path, "/eips") && sawCreate.CompareAndSwap(false, true)
		deletion := r.Method == "DELETE" && strings.Contains(r.URL.Path, "/eips/") && sawDelete.CompareAndSwap(false, true)
		if !create && !deletion {
			return false
		}
		if deletion {
			parts := strings.Split(r.URL.Path, "/")
			saved = api.Object("eips", parts[len(parts)-3], parts[len(parts)-1])
		}
		rec := httptest.NewRecorder()
		api.Backend.ServeHTTP(rec, r)
		if create {
			close(createReached)
			<-createRelease
		} else {
			close(deleteReached)
			<-deleteRelease
		}
		for k, vs := range rec.Header() {
			w.Header()[k] = vs
		}
		w.WriteHeader(rec.Code)
		_, _ = w.Write(rec.Body.Bytes())
		return true
	}
	f, api, db, kubeconfig := newEgressKCFixture(t, intercept)
	accepted, err := f.e.CreateEIP(f.ctx, biz.EgressIntent{Name: "process-crash", IdempotencyKey: "process-crash"})
	if err != nil {
		t.Fatal(err)
	}
	start := func() *networkProcess {
		return startNetworkProcess(t, root, binary, db.RuntimeDSN, kubeconfig, testenv.SigningKey(), "egress")
	}
	first := start()
	select {
	case <-createReached:
	case <-time.After(12 * time.Second):
		t.Fatal("service never reached EIP POST crash point")
	}
	first.kill(t)
	createRelease <- struct{}{}
	second := start()
	waitState := func(state biz.ResourceState) {
		t.Helper()
		awaitNET05A(t, 15*time.Second, func() bool { v, err := f.e.GetEIP(f.ctx, "", accepted.ID); return err == nil && v.State == state })
	}
	waitState(biz.Available)
	api.Backend.Mu.Lock()
	creates := api.Backend.Creates["eips"]
	api.Backend.Mu.Unlock()
	if creates != 1 {
		t.Fatal("crash recovery submitted duplicate EIP", creates)
	}
	current, err := f.e.GetEIP(f.ctx, "", accepted.ID)
	if err != nil || current.LastOperationID != accepted.LastOperationID {
		t.Fatal("process restart lost receipt", err)
	}
	deleting, err := f.e.DeleteEIP(f.ctx, "", accepted.ID)
	if err != nil {
		t.Fatal(err)
	}
	select {
	case <-deleteReached:
	case <-time.After(12 * time.Second):
		t.Fatal("service never reached EIP DELETE crash point")
	}
	second.kill(t)
	deleteRelease <- struct{}{}
	third := start()
	waitState(biz.Deleted)
	current, err = f.e.GetEIP(f.ctx, "", accepted.ID)
	if err != nil || current.LastOperationID != deleting.LastOperationID {
		t.Fatal("delete restart lost operation", err)
	}
	// The same UID late object must be cleaned from the retained tombstone.
	if saved == nil {
		t.Fatal("missing deleted object fixture")
	}
	api.Change("eips", saved, false)
	awaitNET05A(t, 12*time.Second, func() bool {
		api.Backend.Mu.Lock()
		defer api.Backend.Mu.Unlock()
		return api.Backend.Deletes["eips"] == 2
	})
	third.stop(t)
	replay, err := f.e.CreateEIP(context.WithoutCancel(f.ctx), biz.EgressIntent{Name: "process-crash", IdempotencyKey: "process-crash"})
	if err != nil || replay.ID != accepted.ID || replay.State != biz.Provisioning {
		t.Fatal("completed process recovery changed immutable creation receipt", err)
	}
}
