package main

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

func TestInstallationRefusesWrongContextAndClusterBeforeBundleRead(t *testing.T) {
	for _, scenario := range []struct {
		name, context, uid, wantError string
		wantRequests                  int32
	}{
		{"old target context", "kind-kc062", installationClusterUID, "expected current context", 0},
		{"old cluster under new context name", installationContext, "a05787f7-fd36-482d-97ce-daef70e269c6", "cluster UID differs", 1},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			var requests atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				requests.Add(1)
				if r.Method != http.MethodGet || r.URL.Path != "/api/v1/namespaces/kube-system" {
					t.Errorf("request escaped identity check: %s %s", r.Method, r.URL.Path)
					http.Error(w, "unexpected request", http.StatusForbidden)
					return
				}
				w.Header().Set("Content-Type", "application/json")
				fmt.Fprintf(w, `{"apiVersion":"v1","kind":"Namespace","metadata":{"name":"kube-system","uid":%q}}`, scenario.uid)
			}))
			defer server.Close()
			dir := t.TempDir()
			config := filepath.Join(dir, "kubeconfig")
			body := fmt.Sprintf("apiVersion: v1\nkind: Config\ncurrent-context: %s\nclusters:\n- name: target\n  cluster:\n    server: %s\ncontexts:\n- name: %s\n  context:\n    cluster: target\n    user: test\nusers:\n- name: test\n  user: {}\n", scenario.context, server.URL, scenario.context)
			if err := os.WriteFile(config, []byte(body), 0600); err != nil {
				t.Fatal(err)
			}
			output := filepath.Join(dir, "installation.json")
			err := installation([]string{"-kubeconfig", config, "-output", output})
			if err == nil || !strings.Contains(err.Error(), scenario.wantError) {
				t.Fatalf("expected %q, got %v", scenario.wantError, err)
			}
			if requests.Load() != scenario.wantRequests {
				t.Fatalf("requests = %d, want %d", requests.Load(), scenario.wantRequests)
			}
			if _, err := os.Stat(output); !os.IsNotExist(err) {
				t.Fatalf("rejected cluster produced evidence: %v", err)
			}
		})
	}
}
