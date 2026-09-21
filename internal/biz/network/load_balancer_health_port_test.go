package biz

import "testing"

func TestLBExplicitHealthPort(t *testing.T) {
	for _, tc := range []struct {
		name    string
		port    uint32
		missing bool
		valid   bool
	}{
		{"missing", 0, true, false},
		{"zero", 0, false, false},
		{"out-of-range", 65536, false, false},
		{"backend-mismatch", 8080, false, false},
		{"matches-backend-not-listener", 80, false, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			l, repo, ctx := lbTestSetup(t)
			r := lbTestRequest()
			r.Health.Port = &tc.port
			if tc.missing {
				r.Health.Port = nil
			}
			_, err := l.Create(ctx, r)
			if tc.valid {
				if err != nil || repo.accepted[0].Health.Port != 80 || repo.accepted[0].ListenerPort != 8080 {
					t.Fatalf("create: %v %+v", err, repo.accepted)
				}
			} else if ReasonOf(err) != InvalidArgument || len(repo.accepted) != 0 {
				t.Fatalf("invalid port accepted: %v", err)
			}
			_, err = l.Update(ctx, UpdateLoadBalancer{ID: "lb_11111111111111111111111111111111", ExpectedVersion: 1, IdempotencyKey: "update-port", LoadBalancerMutableInput: r.LoadBalancerMutableInput})
			if (tc.valid && err != nil) || (!tc.valid && ReasonOf(err) != InvalidArgument) {
				t.Fatalf("update: %v", err)
			}
		})
	}
}
