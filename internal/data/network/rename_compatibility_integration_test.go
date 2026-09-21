package data_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	networkv1 "github.com/zhangzhe-ctrl/ani-resource-service/api/network/v1"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/data/network"
	controlled "github.com/zhangzhe-ctrl/ani-resource-service/tests/net05a/provider"
	"github.com/zhangzhe-ctrl/ani-resource-service/tests/testenv"
)

// Fixed pre-rename source, separate executables and descriptor registries.
// This controlled PG/HTTP check does not replace real Kubernetes R4 evidence.
func TestResourceRenameOldClientSameDatabaseRollback(t *testing.T) {
	if os.Getenv("NETWORK_TEST_ADMIN_DSN") == "" {
		t.Skip("requires scripts/integration isolated PostgreSQL")
	}
	root, err := filepath.Abs("../../..")
	if err != nil {
		t.Fatal(err)
	}
	oldRoot := os.Getenv("ANI_RESOURCE_BASELINE_ROOT")
	if oldRoot == "" {
		oldRoot = t.TempDir()
		archive := filepath.Join(t.TempDir(), "baseline.tar")
		command := exec.Command("git", "archive", "--output", archive, "66f787bd30134141726c596612501a83cf75bdb7")
		command.Dir = root
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("fixed baseline archive: %v %s", err, output)
		}
		if output, err := exec.Command("tar", "-xf", archive, "-C", oldRoot).CombinedOutput(); err != nil {
			t.Fatalf("baseline extraction: %v %s", err, output)
		}
	}
	build := func(dir, target, name string) string {
		binary := filepath.Join(t.TempDir(), name)
		command := exec.Command("go", "build", "-race", "-trimpath", "-o", binary, target)
		command.Dir = dir
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("build %s: %v %s", name, err, output)
		}
		return binary
	}
	oldBinary := build(oldRoot, "./cmd/ani-network-service", "baseline")
	oldClient := build(oldRoot, "./scripts/lb-api", "old-client")
	candidate := build(root, "./cmd/ani-resource-service", "candidate")
	migrate := func(binary string, owner *pgxpool.Pool, role string) {
		command := exec.Command(binary, "-migrate")
		command.Env = append(os.Environ(), "ANI_NETWORK_MIGRATION_DSN="+owner.Config().ConnString(), "ANI_NETWORK_RUNTIME_ROLE="+role)
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("migration: %v %s", err, output)
		}
	}
	var originalSchema string
	fixture := testenv.NewDatabase(t, func(owner *pgxpool.Pool, role string) {
		migrate(oldBinary, owner, role)
		if err := owner.QueryRow(context.Background(), "SELECT jsonb_agg(to_jsonb(v) ORDER BY version)::text FROM network_schema_version v").Scan(&originalSchema); err != nil {
			t.Fatal(err)
		}
	})
	checkSchema := func() {
		var current string
		if err := fixture.Owner.QueryRow(context.Background(), "SELECT jsonb_agg(to_jsonb(v) ORDER BY version)::text FROM network_schema_version v").Scan(&current); err != nil {
			t.Fatal(err)
		}
		if current != originalSchema {
			t.Fatal("migration versions, checksums or applied timestamps changed")
		}
	}
	checkSchema()
	protocol := controlled.New()
	var armed, captured atomic.Bool
	reached, release := make(chan struct{}), make(chan struct{})
	host := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if armed.Load() && r.Method == "POST" && strings.HasSuffix(r.URL.Path, "/vpcs") && captured.CompareAndSwap(false, true) {
			recorder := httptest.NewRecorder()
			protocol.ServeHTTP(recorder, r)
			close(reached)
			<-release
			for k, v := range recorder.Header() {
				w.Header()[k] = v
			}
			w.WriteHeader(recorder.Code)
			_, _ = w.Write(recorder.Body.Bytes())
			return
		}
		protocol.ServeHTTP(w, r)
	}))
	defer host.Close()
	defer close(release)
	kubeconfig, key := testenv.Kubeconfig(t, host.URL), testenv.SigningKey()
	grpcAddress, adminAddress := freeAddress(t), freeAddress(t)
	start := func(binary string) *networkProcess {
		return startNetworkProcess(t, root, binary, fixture.RuntimeDSN, kubeconfig, key, "subnet", "grpc-address="+grpcAddress, "admin-address="+adminAddress)
	}
	tenant := uuid.NewString()
	call := func(method string, request map[string]any, want string) map[string]any {
		body, _ := json.Marshal(request)
		command := exec.Command(oldClient, "call", "-target", grpcAddress, "-service", "NetworkService", "-method", method)
		command.Stdin = bytes.NewReader(body)
		var stderr bytes.Buffer
		command.Stderr = &stderr
		output, err := command.Output()
		var result struct {
			Code     string         `json:"code"`
			Response map[string]any `json:"response"`
		}
		if json.Unmarshal(output, &result) != nil || result.Code != want || (want == "OK" && err != nil) {
			t.Fatalf("old client %s: %v %s %s", method, err, output, stderr.String())
		}
		return result.Response
	}
	create := func(name, cidr string) map[string]any {
		return map[string]any{"tenant_id": tenant, "name": name, "cidr": cidr, "idempotency_key": "rename-" + name}
	}
	a, b := create("old-a", "10.42.0.0/16"), create("old-b", "10.43.0.0/16")
	first := start(oldBinary)
	receiptA := call("CreateVPC", a, "OK")
	receiptB := call("CreateVPC", b, "OK")
	id := func(r map[string]any) string { return r["vpc"].(map[string]any)["id"].(string) }
	client, closeClient := first.client(t)
	waitRPCState(t, client, tenant, id(receiptA), networkv1.ResourceState_RESOURCE_STATE_AVAILABLE)
	waitRPCState(t, client, tenant, id(receiptB), networkv1.ResourceState_RESOURCE_STATE_AVAILABLE)
	closeClient()
	page := call("ListVPCs", map[string]any{"tenant_id": tenant, "limit": 1}, "OK")
	cursor := page["next_cursor"].(string)
	if cursor == "" {
		t.Fatal("baseline cursor missing")
	}
	pageRequest := map[string]any{"tenant_id": tenant, "limit": 1, "cursor": cursor}
	pageTwo := call("ListVPCs", pageRequest, "OK")
	identities := func() map[string]string {
		protocol.Backend.Mu.Lock()
		defer protocol.Backend.Mu.Unlock()
		result := map[string]string{}
		for k, o := range protocol.Backend.Objects {
			m := o["metadata"].(map[string]any)
			content, _ := json.Marshal(map[string]any{"uid": m["uid"], "labels": m["labels"], "spec": o["spec"]})
			result[k] = string(content)
		}
		return result
	}
	originalObjects := identities()
	first.stop(t)
	second := start(candidate)
	if !reflect.DeepEqual(receiptA, call("CreateVPC", a, "OK")) {
		t.Fatal("old receipt changed on candidate")
	}
	resumedPage := call("ListVPCs", pageRequest, "OK")
	if resumedPage["items"].([]any)[0].(map[string]any)["id"] != pageTwo["items"].([]any)[0].(map[string]any)["id"] {
		t.Fatal("old cursor changed")
	}
	call("GetVPC", map[string]any{"tenant_id": uuid.NewString(), "vpc_id": id(receiptA)}, "NotFound")
	if !reflect.DeepEqual(originalObjects, identities()) {
		t.Fatal("candidate replaced original Provider identity/spec")
	}
	armed.Store(true)
	c := create("candidate-c", "10.44.0.0/16")
	receiptC := call("CreateVPC", c, "OK")
	select {
	case <-reached:
	case <-time.After(8 * time.Second):
		t.Fatal("candidate did not reach persisted Provider-success boundary")
	}
	second.kill(t)
	release <- struct{}{}
	migrate(oldBinary, fixture.Owner, fixture.RuntimeRole)
	checkSchema()
	third := start(oldBinary)
	client, closeClient = third.client(t)
	waitRPCState(t, client, tenant, id(receiptC), networkv1.ResourceState_RESOURCE_STATE_AVAILABLE)
	closeClient()
	if !reflect.DeepEqual(receiptC, call("CreateVPC", c, "OK")) {
		t.Fatal("rollback lost candidate receipt")
	}
	protocol.Backend.Mu.Lock()
	if protocol.Backend.Creates["vpcs"] != 3 || protocol.Backend.Creates["namespaces"] != 1 {
		t.Errorf("duplicate Provider creates: %v", protocol.Backend.Creates)
	}
	protocol.Backend.Mu.Unlock()
	third.stop(t)
	fourth := start(candidate)
	for _, r := range []map[string]any{receiptA, receiptB, receiptC} {
		call("DeleteVPC", map[string]any{"tenant_id": tenant, "vpc_id": id(r)}, "OK")
	}
	client, closeClient = fourth.client(t)
	for _, r := range []map[string]any{receiptA, receiptB, receiptC} {
		waitRPCState(t, client, tenant, id(r), networkv1.ResourceState_RESOURCE_STATE_DELETED)
	}
	closeClient()
	fourth.stop(t)
	checkSchema()
	for name := range identities() {
		if !strings.HasPrefix(name, "namespaces/") {
			t.Fatalf("Provider resource remains after API cleanup: %s", name)
		}
	}
	t.Log("old client: old -> candidate -> old rollback with pending work -> candidate; same DB, endpoint, config, cursor key; identities, receipts, schema timestamps preserved; API cleanup complete")

	// Candidate outbound adapter talks to an independent old generated owner.
	ownerDir, err := os.MkdirTemp("", "rename-owner-")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(ownerDir)
	registry, socket := filepath.Join(ownerDir, "registry.json"), filepath.Join(ownerDir, "owner.sock")
	attachment := biz.Attachment{TenantID: tenant, InstanceID: "instance", SubmissionID: uuid.NewString(), Generation: 1, ID: uuid.NewString(), FinalizationID: uuid.NewString()}
	facts := []map[string]any{{"protocol_version": 1, "tenant_id": tenant, "instance_id": attachment.InstanceID, "submission_id": attachment.SubmissionID, "generation": 1, "attachment_id": attachment.ID, "cluster_id": "test-cluster", "namespace": "tenant-" + tenant, "state": "SUBMISSION_STATE_CLOSED", "finalization_id": attachment.FinalizationID, "pod_uids": []string{"old-pod"}, "controller_uids": []string{"old-controller"}, "closed_at": "2026-09-21T00:00:00Z"}}
	body, _ := json.Marshal(facts)
	if err := os.WriteFile(registry, body, 0600); err != nil {
		t.Fatal(err)
	}
	owner := exec.Command(oldClient, "owner", "-socket", socket, "-registry", registry)
	if err := owner.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = owner.Process.Signal(os.Interrupt); _ = owner.Wait() }()
	deadline := time.Now().Add(5 * time.Second)
	for {
		if _, err := os.Stat(socket); err == nil {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("old owner socket not ready")
		}
		time.Sleep(10 * time.Millisecond)
	}
	consumer, err := data.NewInstanceConsumer("unix://" + socket)
	if err != nil {
		t.Fatal(err)
	}
	defer consumer.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	submission, err := consumer.GetSubmission(ctx, attachment)
	if err != nil || submission.State != "closed" || submission.FinalizationID != attachment.FinalizationID || submission.TenantID != tenant || submission.ClosedAt == nil || !reflect.DeepEqual(submission.PodUIDs, []string{"old-pod"}) || !reflect.DeepEqual(submission.ControllerUIDs, []string{"old-controller"}) {
		t.Fatalf("old reverse consumer changed: %+v %v", submission, err)
	}
	t.Log("candidate outbound adapter -> independent old generated consumer: pass")
}
