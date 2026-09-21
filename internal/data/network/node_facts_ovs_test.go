package data

import (
	"context"
	"fmt"
	"strings"
	"testing"
)

func TestKCBridgeProofRequiresActualOwnershipAndMapping(t *testing.T) {
	for _, tc := range []struct {
		name, bridge, vendor, mapping string
		ready                         bool
	}{
		{"prepared", "br-ens35", "kc-networking", "net.ens35:br-ens35", true},
		{"other_bridge", "br-other", "kc-networking", "net.ens35:br-ens35", false},
		{"other_vendor", "br-ens35", "foreign", "net.ens35:br-ens35", false},
		{"missing_mapping", "br-ens35", "kc-networking", "", false},
		{"wrong_mapping", "br-ens35", "kc-networking", "net.ens35:br-other", false},
		{"duplicate_mapping", "br-ens35", "kc-networking", "net.ens35:br-ens35,net.ens35:br-ens35", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c := &NodeFactsCollector{Run: func(_ context.Context, name string, args ...string) ([]byte, error) {
				cmd := name + " " + strings.Join(args, " ")
				switch cmd {
				case "ovs-vsctl --timeout=3 iface-to-br ens35":
					return []byte(tc.bridge + "\n"), nil
				case "ovs-vsctl --timeout=3 --format=json --columns=external_ids list Bridge br-ens35":
					return []byte(fmt.Sprintf(`{"headings":["external_ids"],"data":[[["map",[["vendor",%q],["purpose","vlan-network"]]]]]}`, tc.vendor)), nil
				case "ovs-vsctl --timeout=3 --format=json --columns=external_ids list Open_vSwitch .":
					return []byte(fmt.Sprintf(`{"headings":["external_ids"],"data":[[["map",[["ovn-bridge-mappings",%q]]]]]}`, tc.mapping)), nil
				default:
					return nil, fmt.Errorf("unexpected non-read command: %s", cmd)
				}
			}}
			bridge, ready, err := c.collectKCBridge(context.Background(), "ens35")
			if err != nil || ready != tc.ready || bridge != tc.bridge {
				t.Fatal(bridge, ready, err)
			}
		})
	}
}
