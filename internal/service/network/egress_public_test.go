package service

import (
	"testing"

	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
)

func TestEIPBindingTargetWireCompatibility(t *testing.T) {
	for _, tc := range []struct {
		name, legacyID, state, targetKind, targetID string
	}{
		{name: "unbound", state: "unbound"},
		{name: "snat-reserved", legacyID: "snat-id", state: "reserved", targetKind: "vpc_snat", targetID: "snat-id"},
		{name: "snat-bound", legacyID: "snat-id", state: "bound", targetKind: "vpc_snat", targetID: "snat-id"},
		{name: "lb-reserved", state: "reserved", targetKind: "load_balancer", targetID: "lb-id"},
		{name: "lb-bound", state: "bound", targetKind: "load_balancer", targetID: "lb-id"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			v := biz.EIP{BindingID: tc.legacyID, BindingState: tc.state, Scope: "public", ManagedBy: "tenant"}
			if tc.targetKind != "" {
				v.BindingTarget = &biz.EIPBindingTarget{Kind: tc.targetKind, ID: tc.targetID, State: tc.state}
			}
			got := wireEIP(v)
			if got.BindingId != tc.legacyID || got.BindingState != tc.state || got.Scope != "public" || got.ManagedBy != "tenant" {
				t.Fatalf("legacy fields drifted: %v", got)
			}
			if tc.targetKind == "" {
				if got.BindingTarget != nil {
					t.Fatal("unbound address has a target", got)
				}
			} else if got.GetBindingTarget().GetKind() != tc.targetKind || got.GetBindingTarget().GetId() != tc.targetID || got.GetBindingTarget().GetState() != tc.state {
				t.Fatal("binding target projection lost claim", got)
			}
		})
	}
}

func TestHistoricalEgressAcceptanceWireAddsPublicMetadata(t *testing.T) {
	eip := wireEIP(biz.EIP{BindingState: "unbound"})
	if eip.Scope != "public" || eip.ManagedBy != "tenant" || eip.BindingTarget != nil || eip.BindingState != "unbound" {
		t.Fatal(eip)
	}
	snat := wireSnat(biz.VPCSnatBinding{})
	if snat.Purpose != "public" || snat.AppliedEnabled != nil {
		t.Fatal(snat)
	}
}
