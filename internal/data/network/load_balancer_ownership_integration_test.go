package data_test

import (
	"github.com/google/uuid"
	"github.com/zhangzhe-ctrl/ani-resource-service/internal/biz/network"
	"testing"
)

func TestLBForeignOccupantsAndUIDReplacementRemainConflicts(t *testing.T) {
	for _, kind := range []string{"service", "foreign-namespace", "nat", "snat", "service-uid", "bound-vpc-namespace"} {
		t.Run(kind, func(t *testing.T) {
			c := &lbControllerFixture{}
			f := newLBAdmissionFixture(t, c.http)
			eip := f.f.eip(t, "ownership-eip")
			request := f.request
			request.Exposure = "public_private"
			request.PublicEIPID = eip.ID
			accepted, err := f.lbs.Create(f.f.ctx, request)
			if err != nil {
				t.Fatal(err)
			}
			lb := lbState(t, f, accepted.LoadBalancer.ID, biz.Available)
			var ns, name, eipName string
			if err = f.f.owner.QueryRow(f.f.ctx, `SELECT namespace,provider_name FROM network_provider_bindings WHERE tenant_id=$1 AND lb_id=$2`, f.f.tenant, lb.ID).Scan(&ns, &name); err != nil {
				t.Fatal(err)
			}
			if err = f.f.owner.QueryRow(f.f.ctx, `SELECT provider_name FROM network_provider_bindings WHERE tenant_id=$1 AND eip_id=$2`, f.f.tenant, eip.ID).Scan(&eipName); err != nil {
				t.Fatal(err)
			}
			f.f.drive(t, func() bool {
				e, err := f.f.e.GetEIP(f.f.ctx, "", eip.ID)
				return err == nil && e.State == biz.Available && e.BindingState == "bound" && e.BindingID == ""
			})
			namespace, objectName, resource := ns, "foreign-"+kind, "services"
			obj := map[string]any{"apiVersion": "v1", "kind": "Service", "metadata": map[string]any{"namespace": ns, "name": objectName, "uid": uuid.NewString(), "annotations": map[string]any{"networking.kubercloud.com/lb_eips": eipName}}, "spec": map[string]any{"type": "LoadBalancer"}}
			if kind == "foreign-namespace" {
				namespace = "unrelated-namespace"
				obj["metadata"].(map[string]any)["namespace"] = namespace
				obj["metadata"].(map[string]any)["annotations"].(map[string]any)["networking.kubercloud.com/lb_eips"] = ns + "/" + eipName
			}
			if kind == "nat" || kind == "snat" {
				resource = kind + "s"
				obj["apiVersion"] = "networking.kubercloud.com/v1"
				if kind == "nat" {
					obj["kind"] = "Nat"
				} else {
					obj["kind"] = "Snat"
				}
				obj["spec"] = map[string]any{"eip": eipName}
			}
			if kind == "service-uid" {
				objectName = name
				obj = f.api.Object("services", ns, name)
				obj["metadata"].(map[string]any)["uid"] = uuid.NewString()
			}
			boundVPC := ""
			if kind == "bound-vpc-namespace" {
				resource, objectName = "eips", eipName
				obj = f.api.Object(resource, ns, objectName)
				bound := obj["status"].(map[string]any)["boundResource"].(map[string]any)
				boundVPC = bound["vpc"].(string)
				bound["vpc"] = "wrong-namespace/" + name
			}
			f.api.Change(resource, obj, false)
			f.f.drive(t, func() bool {
				lb, err = f.lbs.Get(f.f.ctx, "", lb.ID)
				return err == nil && lb.State == biz.Degraded && lb.Reason == biz.ProviderOwnership
			})
			f.f.drive(t, func() bool {
				e, err := f.f.e.GetEIP(f.f.ctx, "", eip.ID)
				return err == nil && e.State == biz.Degraded && e.BindingTarget != nil && e.BindingTarget.ID == lb.ID
			})
			deleted, err := f.lbs.Delete(f.f.ctx, "", lb.ID)
			if err != nil {
				t.Fatal(err)
			}
			f.f.drive(t, func() bool {
				op, err := f.lbs.GetOperation(f.f.ctx, "", deleted.Operation.ID)
				return err == nil && op.State == biz.Blocked && op.Reason == biz.ProviderOwnership
			})
			if f.api.Object(resource, namespace, objectName) == nil {
				t.Fatal("Network deleted foreign resource")
			}
			var occupied int
			if err = f.f.owner.QueryRow(f.f.ctx, `SELECT count(*) FROM network_eip_claims WHERE tenant_id=$1 AND lb_id=$2 AND released_at IS NULL`, f.f.tenant, lb.ID).Scan(&occupied); err != nil || occupied != 1 {
				t.Fatal("foreign occupant released claim", occupied, err)
			}
			// The foreign fixture owner removes only its own object. Deletion then
			// resumes from PG without replacing the registered Service UID.
			if kind == "bound-vpc-namespace" {
				obj["status"].(map[string]any)["boundResource"].(map[string]any)["vpc"] = boundVPC
				f.api.Change(resource, obj, false)
			} else {
				f.api.Change(resource, obj, true)
			}
			lbState(t, f, lb.ID, biz.Deleted)
			if f.api.Object("pods", ns, "lb-backend") == nil {
				t.Fatal("backend owner resource lost")
			}
		})
	}
}

func TestLBInvalidMemberWithdrawsDespiteGeneratedOwnershipConflict(t *testing.T) {
	c := &lbControllerFixture{}
	f := newLBAdmissionFixture(t, c.http)
	created, err := f.lbs.Create(f.f.ctx, f.request)
	if err != nil {
		t.Fatal(err)
	}
	lb := lbState(t, f, created.LoadBalancer.ID, biz.Available)
	var ns, gateway, route string
	if err = f.f.owner.QueryRow(f.f.ctx, `SELECT namespace,provider_name FROM network_provider_bindings WHERE tenant_id=$1 AND lb_id=$2`, f.f.tenant, lb.ID).Scan(&ns, &gateway); err != nil {
		t.Fatal(err)
	}
	if err = f.f.owner.QueryRow(f.f.ctx, `SELECT provider_name FROM network_lb_components WHERE tenant_id=$1 AND lb_id=$2 AND kind='route'`, f.f.tenant, lb.ID).Scan(&route); err != nil {
		t.Fatal(err)
	}
	replacement := f.api.Object("services", ns, gateway)
	replacement["metadata"].(map[string]any)["uid"] = uuid.NewString()
	f.api.Change("services", replacement, false)
	ip := f.api.Object("vnicips", ns, "lb-backend-ip")
	ip["metadata"].(map[string]any)["uid"] = uuid.NewString()
	f.api.Change("vnicips", ip, false)
	f.f.drive(t, func() bool {
		obj := f.api.Object("httproutes", ns, route)
		lb, err = f.lbs.Get(f.f.ctx, "", lb.ID)
		return err == nil && lb.State == biz.Degraded && obj["spec"].(map[string]any)["rules"].([]any)[0].(map[string]any)["backendRefs"] == nil
	})
	if lb.AppliedVersion != 1 || lb.Backends[0].State != "unavailable" {
		t.Fatal("invalid address remained eligible", lb)
	}
	if _, err = f.lbs.Delete(f.f.ctx, "", lb.ID); err != nil {
		t.Fatal(err)
	}
	f.api.Change("services", replacement, true)
	lbState(t, f, lb.ID, biz.Deleted)
}
