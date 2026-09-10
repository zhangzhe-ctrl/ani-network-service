package biz

import "testing"

func TestSubnetGatewayNormalizationAndFingerprint(t *testing.T) {
	r := CreateSubnet{TenantID: "7a7750cf-73b0-49c5-a3b1-4dba42689401", VPCID: "vpc_12345678901234567890123456789012", Name: " 子网 ", CIDR: "10.42.1.0/24", IdempotencyKey: "first"}
	original, err := NewSubnetIntent(r)
	if err != nil || original.Gateway != "10.42.1.1" || original.Name != "子网" {
		t.Fatalf("default: %+v %v", original, err)
	}
	explicit := "10.42.1.1"
	r.Gateway = &explicit
	same, err := NewSubnetIntent(r)
	if err != nil || same.Fingerprint() != original.Fingerprint() {
		t.Fatal("equivalent default gateway changed intent")
	}
	for _, value := range []string{"", "10.42.1.0", "10.42.1.255", "10.42.2.1", "::1", "10.42.1.1/24"} {
		r.Gateway = &value
		if _, err := NewSubnetIntent(r); ReasonOf(err) != InvalidArgument {
			t.Errorf("gateway %q accepted: %v", value, err)
		}
	}
	r.Gateway = nil
	for _, value := range []string{"", "10.42.1.2/24", "10.42.1.0/31", "100.64.0.0/10", "0.0.0.0/0", "172.0.0.0/8", "::/64"} {
		r.CIDR = value
		if _, err := NewSubnetIntent(r); ReasonOf(err) != InvalidArgument {
			t.Errorf("CIDR %q accepted: %v", value, err)
		}
	}
	r.CIDR = "10.42.1.0/30"
	if _, err := NewSubnetIntent(r); err != nil {
		t.Fatal(err)
	}
}
