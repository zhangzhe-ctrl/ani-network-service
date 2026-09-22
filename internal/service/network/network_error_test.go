package service

import (
	"context"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"testing"
)

func TestVPCDependencyDeadlineMapping(t *testing.T) {
	for _, tc := range []struct {
		err  error
		want codes.Code
	}{
		{&biz.Error{Reason: biz.DependencyUnavailable, Message: "Network database connection timed out", Cause: context.DeadlineExceeded}, codes.Unavailable},
		{context.DeadlineExceeded, codes.DeadlineExceeded},
		{context.Canceled, codes.Canceled},
		{biz.Fail(biz.ResourceNotFound, "resource not found"), codes.NotFound},
	} {
		if got := status.Code(rpcError(tc.err)); got != tc.want {
			t.Fatalf("%v: %v want %v", tc.err, got, tc.want)
		}
	}
}
