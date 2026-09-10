package data

import (
	"io"
	"net/http"
	"strings"
	"sync"
)

type providerIO struct {
	mu     sync.Mutex
	values map[string]float64
}

func (p *providerIO) add(key string, n float64) { p.mu.Lock(); defer p.mu.Unlock(); p.values[key] += n }
func (p *providerIO) snapshot() map[string]float64 {
	p.mu.Lock()
	defer p.mu.Unlock()
	out := map[string]float64{}
	for k, v := range p.values {
		out[k] = v
	}
	return out
}

type measuredTransport struct {
	base  http.RoundTripper
	stats *providerIO
}

func (t measuredTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	resource := "other"
	parts := strings.Split(r.URL.Path, "/")
	for _, part := range parts {
		switch part {
		case "vpcs", "subnets", "pods", "vnics", "vnicips", "eips", "namespaces", "snats", "nats", "eipgateways", "vlannetworks", "nodes", "configmaps", "services", "servicecidrs":
			resource = part
		}
	}
	verb := r.Method
	switch verb {
	case "GET", "POST", "DELETE", "PATCH":
	default:
		verb = "OTHER"
	}
	if r.URL.Query().Get("watch") == "true" {
		verb = "WATCH"
	} else if verb == "GET" && len(parts) > 0 && parts[len(parts)-1] == resource {
		verb = "LIST"
	}
	key := verb + "_" + resource
	t.stats.add("requests_"+key+"_total", 1)
	response, err := t.base.RoundTrip(r)
	if err != nil {
		t.stats.add("errors_"+key+"_total", 1)
		return response, err
	}
	if response.StatusCode >= 400 {
		t.stats.add("errors_"+key+"_total", 1)
	}
	response.Body = measuredBody{response.Body, t.stats, key}
	return response, nil
}

type measuredBody struct {
	io.ReadCloser
	stats *providerIO
	key   string
}

func (b measuredBody) Read(p []byte) (int, error) {
	n, err := b.ReadCloser.Read(p)
	b.stats.add("bytes_"+b.key+"_total", float64(n))
	return n, err
}
