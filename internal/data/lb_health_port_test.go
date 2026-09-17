package data

import (
	"github.com/zhangzhe-ctrl/ani-network-service/internal/biz"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"testing"
)

func TestLBHealthPortProvider(t *testing.T) {
	for _, port := range []uint32{0, 8080} {
		r := lbResolved{}
		r.work.Resource.LoadBalancer = &biz.LoadBalancerWork{LoadBalancer: biz.LoadBalancer{Health: biz.LoadBalancerHealth{Port: port}}}
		obj := lbDesiredObject(r, biz.LoadBalancerComponent{Kind: "policy"}, biz.LoadBalancerObservation{})
		got, found, err := unstructured.NestedInt64(obj.Object, "spec", "healthCheck", "active", "overrides", "port")
		if err != nil || found != (port != 0) || got != int64(port) {
			t.Fatalf("port %d: %d %v %v", port, got, found, err)
		}
	}
}
