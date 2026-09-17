package testenv

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"reflect"
	"testing"
)

func TestConfigMapRegistrationPatchPreservesDataAndRequiresIdentity(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func([]map[string]any) []map[string]any
		status int
	}{
		{"registration", func(p []map[string]any) []map[string]any { return p }, 200},
		{"stale_version", func(p []map[string]any) []map[string]any { p[1]["value"] = "old"; return p }, 409},
		{"wrong_uid", func(p []map[string]any) []map[string]any { p[0]["value"] = "other"; return p }, 409},
		{"missing_uid", func(p []map[string]any) []map[string]any { return p[1:] }, 409},
		{"wrong_field", func(p []map[string]any) []map[string]any { p[2]["path"] = "/data"; return p }, 422},
	} {
		t.Run(tc.name, func(t *testing.T) {
			original := map[string]any{"managedDevices": "existing0, ens35", "other-setting": "preserved"}
			object := map[string]any{"metadata": map[string]any{"name": "kcn-config", "namespace": "kcn-system", "uid": "config-uid", "resourceVersion": "10", "annotations": map[string]any{"installer": "preserved"}}, "data": original}
			before, _ := json.Marshal(object)
			server := &KC{Objects: map[string]map[string]any{"configmaps/kcn-system/kcn-config": object}}
			patch := tc.change([]map[string]any{{"op": "test", "path": "/metadata/uid", "value": "config-uid"}, {"op": "test", "path": "/metadata/resourceVersion", "value": "10"}, {"op": "add", "path": "/metadata/annotations", "value": map[string]any{"installer": "preserved", "network.ani.io/device-adoption-fixture": "binding"}}})
			body, _ := json.Marshal(patch)
			request := httptest.NewRequest("PATCH", "/api/v1/namespaces/kcn-system/configmaps/kcn-config", bytes.NewReader(body))
			request.Header.Set("Content-Type", "application/json-patch+json")
			response := httptest.NewRecorder()
			server.ServeHTTP(response, request)
			if response.Code != tc.status {
				t.Fatal(response.Code, response.Body.String())
			}
			after, _ := json.Marshal(object)
			if tc.status != 200 && !bytes.Equal(before, after) {
				t.Fatal("rejected patch mutated fixture")
			}
			if !reflect.DeepEqual(object["data"], map[string]any{"managedDevices": "existing0, ens35", "other-setting": "preserved"}) {
				t.Fatal("registration rewrote data")
			}
		})
	}
}
