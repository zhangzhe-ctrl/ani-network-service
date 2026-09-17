package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	networkv1 "github.com/zhangzhe-ctrl/ani-network-service/api/network/v1"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestTenantSocketCannotSwitchIdentityOrGrantPlatform(t *testing.T) {
	tenant := "123e4567-e89b-12d3-a456-426614174000"
	intercept := fixedCaller(tenant, false)
	invoked := false
	next := func(ctx context.Context, r any) (any, error) {
		invoked = true
		got, _, err := (biz.ContextEgressAuthorization{}).Tenant(ctx, "")
		if err != nil || got != tenant {
			t.Fatal("fixed tenant missing", got, err)
		}
		if _, err = (biz.ContextEgressAuthorization{}).Platform(ctx); biz.ReasonOf(err) != biz.PermissionDenied {
			t.Fatal("tenant socket granted platform", err)
		}
		if r.(*networkv1.CreateVPCRequest).TenantId != tenant {
			t.Fatal("legacy Network request was not scoped")
		}
		return nil, nil
	}
	if _, err := intercept(context.Background(), &networkv1.CreateVPCRequest{}, &grpc.UnaryServerInfo{}, next); err != nil || !invoked {
		t.Fatal(err)
	}
	invoked = false
	if _, err := intercept(context.Background(), &networkv1.CreateVPCRequest{TenantId: "123e4567-e89b-12d3-a456-426614174001"}, &grpc.UnaryServerInfo{}, next); status.Code(err) != codes.PermissionDenied || invoked {
		t.Fatal("request changed trusted identity", err)
	}
	// Headers and body attribution are not read by the trusted context adapter.
	_, err := fixedCaller("", true)(context.Background(), nil, &grpc.UnaryServerInfo{}, func(ctx context.Context, _ any) (any, error) {
		if _, err := (biz.ContextEgressAuthorization{}).Platform(ctx); err != nil {
			t.Fatal(err)
		}
		if _, _, err := (biz.ContextEgressAuthorization{}).Tenant(ctx, tenant); biz.ReasonOf(err) != biz.PermissionDenied {
			t.Fatal("platform socket implicitly delegated tenant", err)
		}
		return nil, nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
func TestSocketRequiresPrivateDirectoryAndPreservesExistingPath(t *testing.T) {
	dir := t.TempDir()
	if err := os.Chmod(dir, 0755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "api.sock")
	if l, err := localSocket(path); err == nil {
		l.Close()
		t.Fatal("public directory accepted")
	}
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	l, err := localSocket(path)
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	before, err := os.Lstat(path)
	if err != nil || before.Mode().Perm() != 0600 {
		t.Fatal(before, err)
	}
	if other, err := localSocket(path); err == nil {
		other.Close()
		t.Fatal("existing endpoint overwritten")
	}
}
func TestOwnerMatchesCompleteSubmissionIdentity(t *testing.T) {
	path := filepath.Join(t.TempDir(), "owner.json")
	body := `[{"protocol_version":1,"tenant_id":"tenant","instance_id":"instance","attachment_id":"attachment","submission_id":"submission","generation":"2","cluster_id":"cluster","namespace":"namespace","state":"SUBMISSION_STATE_CLOSING","finalization_id":"final","pod_uids":["pod-uid"]}]`
	if err := os.WriteFile(path, []byte(body), 0600); err != nil {
		t.Fatal(err)
	}
	owner := &registryOwner{path: path}
	request := &networkv1.GetSubmissionRequest{ProtocolVersion: 1, TenantId: "tenant", InstanceId: "instance", AttachmentId: "attachment", SubmissionId: "submission", Generation: 2, ExpectedFinalizationId: "final"}
	if response, err := owner.GetSubmission(context.Background(), request); err != nil || response.PodUids[0] != "pod-uid" {
		t.Fatal(response, err)
	}
	request.ExpectedFinalizationId = "other"
	if _, err := owner.GetSubmission(context.Background(), request); status.Code(err) != codes.FailedPrecondition {
		t.Fatal(err)
	}
	request.TenantId = "other"
	if _, err := owner.GetSubmission(context.Background(), request); status.Code(err) != codes.NotFound {
		t.Fatal(err)
	}
}
