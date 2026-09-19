package data

import (
	"context"
	"errors"
	"fmt"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"testing"
	"time"
)

func TestVPCConnectionDeadlineIsDependencyFailure(t *testing.T) {
	cause := fmt.Errorf("dial timeout: %w", context.DeadlineExceeded)
	err := vpcQueryFailure(context.Background(), cause)
	if biz.ReasonOf(err) != biz.DependencyUnavailable || !errors.Is(err, cause) {
		t.Fatalf("dependency classification/cause: %v", err)
	}
	expired, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	err = vpcQueryFailure(expired, cause)
	if biz.ReasonOf(err) != "" || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("caller deadline: %v", err)
	}
	if err := vpcQueryFailure(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
}
