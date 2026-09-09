package biz_test

import (
	"testing"

	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
)

func TestTenantCanDescribeAnExplicitPrivateVPC(t *testing.T) {
	intent, err := biz.NewVPCIntent("7a7750cf-73b0-49c5-a3b1-4dba42689401", "  研发网络  ", "10.42.0.0/16", "研发环境", "request-01")
	if err != nil {
		t.Fatal(err)
	}
	if intent.Name != "研发网络" || intent.CIDR != "10.42.0.0/16" || intent.Description != "研发环境" {
		t.Fatalf("unexpected normalized product intent: %+v", intent)
	}
	if _, err := biz.NewVPCIntent("", "network", "10.42.0.0/16", "", "request-01"); biz.ReasonOf(err) != biz.TenantRequired {
		t.Fatalf("missing tenant must fail without fallback, got %v", err)
	}
}
