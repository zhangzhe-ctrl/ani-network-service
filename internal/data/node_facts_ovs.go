package data

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
)

// collectKCBridge proves that the interface belongs to kc's actual bridge and
// local-network mapping. KC's node annotation alone cannot prove OVS wiring.
func (c *NodeFactsCollector) collectKCBridge(ctx context.Context, device string) (string, bool, error) {
	run := func(args ...string) ([]byte, error) {
		body, err := c.Run(ctx, "ovs-vsctl", append([]string{"--timeout=3"}, args...)...)
		if err != nil || len(body) > 4<<20 {
			return nil, fmt.Errorf("read bounded OVS bridge facts")
		}
		return body, nil
	}
	body, err := run("iface-to-br", device)
	if err != nil {
		return "", false, err
	}
	bridge := strings.TrimSpace(string(body))
	if bridge != "br-"+device {
		return bridge, false, nil
	}
	readMap := func(table string, record string) (map[string]string, error) {
		body, err := run("--format=json", "--columns=external_ids", "list", table, record)
		if err != nil {
			return nil, err
		}
		var result struct {
			Headings []string `json:"headings"`
			Data     [][]any  `json:"data"`
		}
		if json.Unmarshal(body, &result) != nil || !slices.Equal(result.Headings, []string{"external_ids"}) || len(result.Data) != 1 || len(result.Data[0]) != 1 {
			return nil, fmt.Errorf("invalid OVS external IDs")
		}
		value, ok := result.Data[0][0].([]any)
		if !ok || len(value) != 2 || value[0] != "map" {
			return nil, fmt.Errorf("invalid OVS external IDs map")
		}
		entries, ok := value[1].([]any)
		if !ok {
			return nil, fmt.Errorf("invalid OVS external IDs entries")
		}
		values := map[string]string{}
		for _, entry := range entries {
			pair, ok := entry.([]any)
			if !ok || len(pair) != 2 {
				return nil, fmt.Errorf("invalid OVS external IDs pair")
			}
			key, keyOK := pair[0].(string)
			value, valueOK := pair[1].(string)
			_, duplicate := values[key]
			if !keyOK || !valueOK || duplicate {
				return nil, fmt.Errorf("invalid OVS external IDs value")
			}
			values[key] = value
		}
		return values, nil
	}
	ids, err := readMap("Bridge", bridge)
	if err != nil {
		return bridge, false, err
	}
	if ids["vendor"] != "kc-networking" || ids["purpose"] != "vlan-network" {
		return bridge, false, nil
	}
	global, err := readMap("Open_vSwitch", ".")
	if err != nil {
		return bridge, false, err
	}
	matches := 0
	for _, mapping := range strings.Split(global["ovn-bridge-mappings"], ",") {
		network, target, ok := strings.Cut(strings.TrimSpace(mapping), ":")
		if network == "net."+device {
			if !ok || target != bridge {
				return bridge, false, nil
			}
			matches++
		}
	}
	return bridge, matches == 1, nil
}
