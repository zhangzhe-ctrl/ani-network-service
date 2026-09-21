package biz

import (
	"context"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestEgressAuthorizationRequiresTrustedContextAndExplicitDelegation(t *testing.T) {
	a := ContextEgressAuthorization{}
	tenant := "11111111-1111-4111-8111-111111111111"
	other := "22222222-2222-4222-8222-222222222222"
	if _, _, err := a.Tenant(context.Background(), tenant); ReasonOf(err) != PermissionDenied {
		t.Fatal(err)
	}
	ctx := WithEgressCaller(context.Background(), EgressCaller{TenantID: tenant, PlatformAdministrator: true})
	if got, _, err := a.Tenant(ctx, ""); err != nil || got != tenant {
		t.Fatalf("default tenant: %s %v", got, err)
	}
	if _, _, err := a.Tenant(ctx, other); ReasonOf(err) != PermissionDenied {
		t.Fatalf("platform admin is not tenant delegation: %v", err)
	}
	if _, err := a.Platform(ctx); err != nil {
		t.Fatal(err)
	}
	ctx = WithEgressCaller(context.Background(), EgressCaller{TenantID: tenant, DelegatedTenants: []string{other}})
	if got, _, err := a.Tenant(ctx, other); err != nil || got != other {
		t.Fatalf("delegation: %s %v", got, err)
	}
	if _, err := a.Platform(ctx); ReasonOf(err) != PermissionDenied {
		t.Fatal("delegation must not grant platform access")
	}
	if _, _, err := a.Tenant(ctx, "not-a-tenant"); ReasonOf(err) != TenantRequired {
		t.Fatal(err)
	}
}
func TestPublicPoolTopologyAndReservations(t *testing.T) {
	base := PublicPoolConfig{Mode: "overlay", GatewayID: "egw_" + strings.Repeat("1", 32), CIDR: "198.51.100.0/24", OVNGatewayIP: "198.51.100.1"}
	p, err := NormalizePublicPool(base)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(p.ExcludedIPs, []string{"198.51.100.1"}) {
		t.Fatal(p)
	}
	underlay := base
	underlay.Mode = "underlay"
	underlay.VlanNetworkID = "vlan_" + strings.Repeat("2", 32)
	underlay.UpstreamGatewayIP = "198.51.100.254"
	p, err = NormalizePublicPool(underlay)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(p.ExcludedIPs, []string{"198.51.100.1", "198.51.100.254"}) {
		t.Fatal(p)
	}
	for name, mutate := range map[string]func(*PublicPoolConfig){
		"overlay_has_vlan":             func(v *PublicPoolConfig) { v.VlanNetworkID = underlay.VlanNetworkID },
		"overlay_has_physical_gateway": func(v *PublicPoolConfig) { v.UpstreamGatewayIP = "198.51.100.254" },
		"missing_underlay":             func(v *PublicPoolConfig) { v.Mode = "underlay" },
		"unknown_mode":                 func(v *PublicPoolConfig) { v.Mode = "VLAN" },
		"noncanonical_cidr":            func(v *PublicPoolConfig) { v.CIDR = "198.51.100.1/24" },
		"ipv6":                         func(v *PublicPoolConfig) { v.CIDR = "2001:db8::/64" },
		"network_gateway":              func(v *PublicPoolConfig) { v.OVNGatewayIP = "198.51.100.0" },
		"broadcast_gateway":            func(v *PublicPoolConfig) { v.OVNGatewayIP = "198.51.100.255" },
		"reversed_range":               func(v *PublicPoolConfig) { v.ExcludedIPs = []string{"198.51.100.9..198.51.100.2"} },
		"out_of_pool":                  func(v *PublicPoolConfig) { v.ExcludedIPs = []string{"203.0.113.1"} },
	} {
		t.Run(name, func(t *testing.T) {
			v := base
			mutate(&v)
			if _, err := NormalizePublicPool(v); ReasonOf(err) != InvalidArgument {
				t.Fatal("accepted illegal topology", err)
			}
		})
	}
	underlay.UpstreamGatewayIP = underlay.OVNGatewayIP
	if _, err := NormalizePublicPool(underlay); err == nil {
		t.Fatal("same physical and OVN gateway accepted")
	}
}
func TestNodeInterfaceFactsDoNotTreatManagementOrStaleLinksAsCandidates(t *testing.T) {
	now := time.Now().UTC()
	fresh := NodeInterface{NodeName: "n1", NodeUID: "uid1", Name: "ens224", Kind: "device", ObservedAt: now, Addresses: []string{"fe80::1/64", "169.254.1.1/16"}}
	cases := []struct {
		name   string
		change func(*NodeInterface)
	}{
		{"address", func(v *NodeInterface) { v.Addresses = append(v.Addresses, "10.0.0.1/24") }},
		{"management", func(v *NodeInterface) { v.Management = true }},
		{"default_route", func(v *NodeInterface) { v.DefaultRoute = true }},
		{"veth", func(v *NodeInterface) { v.Kind = "veth" }},
		{"bridge", func(v *NodeInterface) { v.Master = "br0" }},
		{"ovs", func(v *NodeInterface) { v.OVSManaged = true }},
		{"managed", func(v *NodeInterface) { v.KCManaged = true }},
		{"stale", func(v *NodeInterface) { v.ObservedAt = now.Add(-61 * time.Second) }},
		{"future", func(v *NodeInterface) { v.ObservedAt = now.Add(time.Second) }},
		{"uid_missing", func(v *NodeInterface) { v.NodeUID = "" }},
	}
	if !FilterNodeInterfaces([]NodeInterface{fresh}, now, time.Minute)[0].Selectable {
		t.Fatal("link-local-only physical device rejected")
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			v := fresh
			c.change(&v)
			r := FilterNodeInterfaces([]NodeInterface{v}, now, time.Minute)[0]
			if r.Selectable || len(r.UnavailableReasons) == 0 {
				t.Fatal(r)
			}
			if !r.ObservedAt.Equal(v.ObservedAt) {
				t.Fatal("filter renewed facts")
			}
		})
	}
}

func TestPreManagedDeviceRequiresCompleteKCProof(t *testing.T) {
	now := time.Now().UTC()
	fresh := NodeInterface{NodeName: "ani-01", NodeUID: "node-1", Name: "ens35", Kind: "device", MAC: "00:0c:29:e2:f0:2b", Master: "ovs-system", OVSManaged: true, KCManaged: true, KCConfigured: true, KCBridgeReady: true, KCConfigUID: "config-uid", LinkUp: true, Carrier: true, ObservedAt: now}
	if !FilterNodeInterfaces([]NodeInterface{fresh}, now, time.Minute)[0].Selectable {
		t.Fatal("already prepared kc device is not selectable for registration")
	}
	cases := []struct {
		name   string
		change func(*NodeInterface)
	}{
		{"unconfigured", func(v *NodeInterface) { v.KCConfigured = false }},
		{"not_managed", func(v *NodeInterface) { v.KCManaged = false }},
		{"unknown_config", func(v *NodeInterface) { v.KCConfigUID = "" }},
		{"wrong_bridge_or_mapping", func(v *NodeInterface) { v.KCBridgeReady = false }},
		{"another_owner", func(v *NodeInterface) { v.KCDeviceOwner = "foreign-binding" }},
		{"bond", func(v *NodeInterface) { v.Master = "bond0" }},
		{"no_mac", func(v *NodeInterface) { v.MAC = "" }},
		{"link_down", func(v *NodeInterface) { v.LinkUp = false }},
		{"no_carrier", func(v *NodeInterface) { v.Carrier = false }},
		{"management_bridge", func(v *NodeInterface) { v.Management = true }},
		{"address", func(v *NodeInterface) { v.Addresses = []string{"172.16.102.200/24"} }},
		{"stale", func(v *NodeInterface) { v.ObservedAt = now.Add(-2 * time.Minute) }},
		{"external_vlan", func(v *NodeInterface) { v.UnavailableReasons = []string{"provider_vlan_in_use"} }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			v := fresh
			tc.change(&v)
			if FilterNodeInterfaces([]NodeInterface{v}, now, time.Minute)[0].Selectable {
				t.Fatal("unsafe pre-managed device accepted", v)
			}
		})
	}
}
func TestEgressFingerprintsPreserveIntentAndIgnoreInfrastructureRefresh(t *testing.T) {
	i := EgressIntent{TenantID: "tenant", Kind: "create_eip", Name: "eip", IdempotencyKey: "one"}
	h := i.Fingerprint()
	i.IdempotencyKey = "two"
	if h != i.Fingerprint() {
		t.Fatal("key in payload fingerprint")
	}
	i.Name = "different"
	if h == i.Fingerprint() {
		t.Fatal("different intent same fingerprint")
	}
	p := PlatformIntent{Kind: "adopt_device", Device: &DeviceConfig{DeviceName: "ens224", InventoryFingerprint: strings.Repeat("a", 64)}}
	h = p.Fingerprint()
	p.Device.Nodes = []NodeInterface{{ObservedAt: time.Now()}}
	if h != p.Fingerprint() {
		t.Fatal("discovery after replay changed fingerprint")
	}
	p.Device.InventoryFingerprint = strings.Repeat("b", 64)
	if h == p.Fingerprint() {
		t.Fatal("node set/facts fingerprint omitted")
	}
}
