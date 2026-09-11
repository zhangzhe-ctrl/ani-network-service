package data_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"github.com/zhangzhe-ctrl/ani-network-service/internal/data"
	controlled "github.com/zhangzhe-ctrl/ani-network-service/tests/net05a/provider"
	"k8s.io/client-go/rest"
)

func TestEgressKCDeviceAdoptionPartialFactsAndUntaggedVlan(t *testing.T) {
	p, owner := database(t)
	api := controlled.New()
	host := httptest.NewServer(api)
	defer host.Close()
	provider, err := data.NewKCProvider(p, &rest.Config{Host: host.URL, QPS: 1000, Burst: 1000})
	if err != nil {
		t.Fatal(err)
	}
	p.UseEgressInfrastructure(provider)
	e, err := biz.NewEgress(p, provider, biz.ContextEgressAuthorization{}, []byte("0123456789abcdef0123456789abcdef"), time.Minute, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	policy := biz.DefaultWorkerPolicy()
	policy.ObserveEvery = 50 * time.Millisecond
	policy.RetryMin = time.Millisecond
	policy.RetryMax = 10 * time.Millisecond
	w, err := biz.NewWorker(p, provider, uuid.NewString(), policy)
	if err != nil {
		t.Fatal(err)
	}
	f := &egressFixture{p: p, owner: owner, e: e, w: w, ctx: biz.WithEgressCaller(context.Background(), biz.EgressCaller{PlatformAdministrator: true})}
	nodes := map[string]string{"node-a": uuid.NewString(), "node-b": uuid.NewString()}
	facts := func(name string, managed bool, at time.Time) {
		uid := nodes[name]
		annotation := `{}`
		if managed {
			annotation = `{"fixture0":true}`
		}
		api.Change("nodes", map[string]any{"apiVersion": "v1", "kind": "Node", "metadata": map[string]any{"name": name, "uid": uid, "annotations": map[string]any{"networking.kubercloud.com/managed_netdevs": annotation}}}, false)
		doc := data.NodeFactsDocument{Version: 1, NodeName: name, NodeUID: uid, CollectedAt: at, Interfaces: []biz.NodeInterface{{NodeName: name, NodeUID: uid, Name: "fixture0", Kind: "device", OVSManaged: managed}}}
		body, _ := json.Marshal(doc)
		api.Change("configmaps", map[string]any{"apiVersion": "v1", "kind": "ConfigMap", "metadata": map[string]any{"name": "facts-" + name, "namespace": "kcn-system", "uid": "facts-uid-" + name, "labels": map[string]any{"network.ani.io/managed-by": "ani-network-node-facts", "network.ani.io/node-uid": uid}}, "data": map[string]any{"facts.json": string(body)}}, false)
	}
	facts("node-a", false, time.Now())
	facts("node-b", false, time.Now())
	api.Change("configmaps", map[string]any{"apiVersion": "v1", "kind": "ConfigMap", "metadata": map[string]any{"name": "kcn-config", "namespace": "kcn-system", "uid": "shared-config-uid", "annotations": map[string]any{"other-owner": "preserved"}}, "data": map[string]any{"managedDevices": "existing0", "other-setting": "preserved"}}, false)
	inv, err := e.ListNodeInterfaces(f.ctx, "")
	if err != nil || len(inv.Items) != 2 || !inv.Items[0].Selectable || !inv.Items[1].Selectable {
		t.Fatal("fixture device discovery", inv, err)
	}
	device, err := e.CreatePlatform(f.ctx, biz.PlatformIntent{Kind: "adopt_device", Name: "fixture-adoption", IdempotencyKey: "adopt", Device: &biz.DeviceConfig{DeviceName: "fixture0", InventoryFingerprint: inv.Fingerprint}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = w.Step(f.ctx); err != nil {
		t.Fatal(err)
	}
	current, err := e.GetPlatform(f.ctx, "device", device.ID)
	if err != nil || current.State == biz.Available {
		t.Fatal("unapplied device claimed ready", err)
	}
	cm := api.Object("configmaps", "kcn-system", "kcn-config")
	if cm["data"].(map[string]any)["managedDevices"] != "existing0,fixture0" || cm["data"].(map[string]any)["other-setting"] != "preserved" || cm["metadata"].(map[string]any)["annotations"].(map[string]any)["other-owner"] != "preserved" {
		t.Fatal("device adoption clobbered shared config", cm)
	}
	facts("node-a", true, time.Now())
	f.drive(t, func() bool {
		v, err := e.GetPlatform(f.ctx, "device", device.ID)
		if err != nil {
			return false
		}
		n := 0
		for _, item := range v.Device.Nodes {
			if item.KCManaged {
				n++
			}
		}
		return n == 1 && v.State != biz.Available
	})
	if _, err = e.CreatePlatform(f.ctx, biz.PlatformIntent{Kind: "create_vlan", Name: "too-early", IdempotencyKey: "too-early", Vlan: &biz.VlanConfig{DeviceID: device.ID, VlanID: 0}}); biz.ReasonOf(err) != biz.PublicEgressNotReady {
		t.Fatal("partial adoption admitted VLAN", err)
	}
	facts("node-b", true, time.Now())
	f.drive(t, func() bool {
		v, err := e.GetPlatform(f.ctx, "device", device.ID)
		return err == nil && v.State == biz.Available
	})
	vlan := f.platform(t, biz.PlatformIntent{Kind: "create_vlan", Name: "untagged", IdempotencyKey: "vlan", Vlan: &biz.VlanConfig{DeviceID: device.ID, VlanID: 0}})
	cr := api.Object("vlannetworks", "", "vlan-"+vlan.ID[5:])
	if fmt.Sprint(cr["spec"].(map[string]any)["vlanID"]) != "0" || cr["spec"].(map[string]any)["devName"] != "fixture0" {
		t.Fatal("VLAN zero render", cr)
	}
	facts("node-b", true, time.Now().Add(-2*time.Minute))
	f.drive(t, func() bool {
		v, err := e.GetPlatform(f.ctx, "vlan", vlan.ID)
		return err == nil && v.State == biz.Degraded
	})
}
