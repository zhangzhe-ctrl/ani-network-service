package biz

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestIntranetPoolRejectsPublicGatewayAndInvalidDestinations(t *testing.T) {
	good := PublicPoolConfig{CIDR: "10.232.254.0/24", OVNGatewayIP: "10.232.254.1", DefaultVPCName: "kcn-cluster", DefaultVPCUID: "gateway-uid", IntranetNetworks: []string{"10.96.0.0/12", "10.96.0.0/12"}}
	normalized, err := NormalizeIntranetPool(good)
	if err != nil || normalized.Scope != "intranet" || len(normalized.ExcludedIPs) != 1 || len(normalized.IntranetNetworks) != 1 {
		t.Fatal(normalized, err)
	}
	cases := []struct {
		name   string
		mutate func(*PublicPoolConfig)
	}{
		{"public gateway", func(p *PublicPoolConfig) { p.GatewayID = "egw_" + strings.Repeat("a", 32) }},
		{"scope", func(p *PublicPoolConfig) { p.Scope = "public" }},
		{"default uid", func(p *PublicPoolConfig) { p.DefaultVPCUID = "" }},
		{"namespace injection", func(p *PublicPoolConfig) { p.DefaultVPCName = "other/kcn-cluster" }},
		{"default route", func(p *PublicPoolConfig) { p.IntranetNetworks = []string{"0.0.0.0/0"} }},
		{"unmasked", func(p *PublicPoolConfig) { p.IntranetNetworks = []string{"10.96.0.1/12"} }},
		{"underlay", func(p *PublicPoolConfig) { p.Mode = "underlay" }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := good
			tc.mutate(&p)
			if _, err := NormalizeIntranetPool(p); err == nil {
				t.Fatal("invalid intranet intent accepted")
			}
		})
	}
}
func TestIntranetEvidenceCannotAuthorizePublicAndLegacyScopeRemainsValid(t *testing.T) {
	now := time.Now()
	ev := PublicPoolVerification{ProviderSourceRevision: strings.Repeat("a", 40), ProviderImageDigests: []string{"sha256:" + strings.Repeat("b", 64)}, TopologyFingerprint: strings.Repeat("c", 64), EvidenceReference: "controlled provider contract", Scope: IntranetVerificationScope, VerifiedAt: now.Add(-time.Second), ExpiresAt: now.Add(time.Hour)}
	if err := ValidatePoolVerificationForScope(ev, "intranet", now); err != nil {
		t.Fatal(err)
	}
	if ValidatePoolVerificationForScope(ev, "public", now) == nil {
		t.Fatal("intranet proof authorized public")
	}
	ev.Scope = "legacy public overlay acceptance"
	if err := ValidatePoolVerificationForScope(ev, "public", now); err != nil {
		t.Fatal(err)
	}
	if ValidatePoolVerificationForScope(ev, "intranet", now) == nil {
		t.Fatal("public proof authorized intranet")
	}
}
func TestPublicPoolNewFieldsPreserveFingerprintShape(t *testing.T) {
	p := PublicPoolConfig{Mode: "overlay", GatewayID: "egw_" + strings.Repeat("a", 32), CIDR: "192.0.2.0/24", OVNGatewayIP: "192.0.2.1"}
	raw, err := json.Marshal(p)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"Scope", "DefaultVPCName", "DefaultVPCUID", "IntranetNetworks"} {
		if _, exists := fields[field]; exists {
			t.Fatal("new omitted field changes accepted public fingerprints", field)
		}
	}
}
