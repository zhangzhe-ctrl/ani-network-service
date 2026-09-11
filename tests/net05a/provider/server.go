// Package provider is a controlled HTTP List/Watch fixture. It is not a kc or
// data-plane implementation and never supplies real-cluster acceptance evidence.
package provider

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/zhangzhe-ctrl/ani-network-service/tests/testenv"
)

type event struct {
	Type   string `json:"type"`
	Object any    `json:"object"`
}
type subscriber struct {
	gvr    string
	events chan event
	done   chan struct{}
}
type page struct {
	items    []any
	revision int64
	expires  time.Time
}
type Server struct {
	Backend      *testenv.KC
	mu           sync.Mutex
	revision     int64
	blackhole    bool
	subscribers  map[*subscriber]bool
	failures     map[string][]int
	requests     map[string]int64
	bytes        map[string]int64
	pages        map[string]page
	continuation int64
	HoldList     <-chan struct{}
	ListCaptured chan<- struct{}
}

func New() *Server {
	return &Server{Backend: &testenv.KC{Objects: map[string]map[string]any{}, Creates: map[string]int{}, Deletes: map[string]int{}}, revision: 1, subscribers: map[*subscriber]bool{}, failures: map[string][]int{}, requests: map[string]int64{}, bytes: map[string]int64{}, pages: map[string]page{}}
}
func (s *Server) Fail(verb, gvr string, codes ...int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failures[verb+"/"+gvr] = append([]int{}, codes...)
}
func (s *Server) Counts() (map[string]int64, map[string]int64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	r, b := map[string]int64{}, map[string]int64{}
	for k, v := range s.requests {
		r[k] = v
	}
	for k, v := range s.bytes {
		b[k] = v
	}
	return r, b
}
func (s *Server) Disconnect(code int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for sub := range s.subscribers {
		if code != 0 {
			sub.events <- event{"ERROR", map[string]any{"apiVersion": "v1", "kind": "Status", "code": code, "reason": "Expired", "status": "Failure"}}
		} else {
			close(sub.done)
		}
		delete(s.subscribers, sub)
	}
}
func clone(value map[string]any) map[string]any {
	b, _ := json.Marshal(value)
	var out map[string]any
	_ = json.Unmarshal(b, &out)
	return out
}
func (s *Server) Change(gvr string, object map[string]any, deleted bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.revision++
	obj := clone(object)
	m := obj["metadata"].(map[string]any)
	m["resourceVersion"] = strconv.FormatInt(s.revision, 10)
	ns, _ := m["namespace"].(string)
	name := m["name"].(string)
	key := gvr + "/" + ns + "/" + name
	s.Backend.Mu.Lock()
	_, present := s.Backend.Objects[key]
	if deleted {
		delete(s.Backend.Objects, key)
	} else {
		s.Backend.Objects[key] = obj
	}
	s.Backend.Mu.Unlock()
	typ := "MODIFIED"
	if !present {
		typ = "ADDED"
	}
	if deleted {
		typ = "DELETED"
	}
	s.publish(gvr, event{typ, obj})
}
func (s *Server) Blackhole(enabled bool) { s.mu.Lock(); defer s.mu.Unlock(); s.blackhole = enabled }
func (s *Server) publish(gvr string, e event) {
	if s.blackhole {
		return
	}
	for sub := range s.subscribers {
		if sub.gvr == gvr {
			select {
			case sub.events <- e:
			default:
				close(sub.done)
				delete(s.subscribers, sub)
			}
		}
	}
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	offset := 3
	if parts[0] == "api" {
		offset = 2
	}
	if len(parts) <= offset {
		http.NotFound(w, r)
		return
	}
	gvr, ns, name := parts[offset], "", ""
	if gvr == "namespaces" && len(parts) > offset+2 {
		ns = parts[offset+1]
		gvr = parts[offset+2]
		if len(parts) > offset+3 {
			name = parts[offset+3]
		}
	} else if len(parts) > offset+1 {
		name = parts[offset+1]
	}
	verb := r.Method
	if verb == "GET" && name == "" {
		verb = "LIST"
	}
	if r.URL.Query().Get("watch") == "true" {
		verb = "WATCH"
	}
	key := verb + "/" + gvr
	s.mu.Lock()
	s.requests[key]++
	codes := s.failures[key]
	if len(codes) > 0 {
		s.failures[key] = codes[1:]
	}
	s.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	if len(codes) > 0 {
		w.WriteHeader(codes[0])
		_ = json.NewEncoder(w).Encode(map[string]any{"apiVersion": "v1", "kind": "Status", "code": codes[0], "status": "Failure", "reason": http.StatusText(codes[0])})
		return
	}
	write := func(value any) {
		b, _ := json.Marshal(value)
		b = append(b, '\n')
		_, _ = w.Write(b)
		s.mu.Lock()
		s.bytes[key] += int64(len(b))
		s.mu.Unlock()
	}
	if verb == "WATCH" {
		sub := &subscriber{gvr, make(chan event, 2048), make(chan struct{})}
		s.mu.Lock()
		s.subscribers[sub] = true
		s.mu.Unlock()
		defer func() { s.mu.Lock(); delete(s.subscribers, sub); s.mu.Unlock() }()
		w.WriteHeader(200)
		w.(http.Flusher).Flush()
		if r.URL.Query().Get("sendInitialEvents") == "true" {
			s.mu.Lock()
			rev := s.revision
			s.Backend.Mu.Lock()
			initial := []map[string]any{}
			for k, v := range s.Backend.Objects {
				if strings.HasPrefix(k, gvr+"/") {
					initial = append(initial, clone(v))
				}
			}
			s.Backend.Mu.Unlock()
			s.mu.Unlock()
			for _, obj := range initial {
				write(event{"ADDED", obj})
			}
			version := "networking.kubercloud.com/v1"
			if gvr == "pods" || gvr == "nodes" || gvr == "configmaps" || gvr == "services" {
				version = "v1"
			}
			kind := map[string]string{"vpcs": "VPC", "subnets": "Subnet", "pods": "Pod", "vnics": "VNic", "vnicips": "VNicIP", "eips": "EIP", "snats": "Snat", "nats": "Nat", "eipgateways": "EIPGateway", "vlannetworks": "VlanNetwork", "nodes": "Node", "configmaps": "ConfigMap", "services": "Service", "servicecidrs": "ServiceCIDR"}[gvr]
			write(event{"BOOKMARK", map[string]any{"apiVersion": version, "kind": kind, "metadata": map[string]any{"resourceVersion": strconv.FormatInt(rev, 10), "annotations": map[string]any{"k8s.io/initial-events-end": "true"}}}})
			w.(http.Flusher).Flush()
		}
		for {
			select {
			case <-r.Context().Done():
				return
			case <-sub.done:
				return
			case e := <-sub.events:
				write(e)
				w.(http.Flusher).Flush()
				if e.Type == "ERROR" {
					return
				}
			}
		}
	}
	if verb == "LIST" {
		s.mu.Lock()
		rev := s.revision
		token := r.URL.Query().Get("continue")
		var items []any
		if token != "" {
			p, ok := s.pages[token]
			delete(s.pages, token)
			if !ok || time.Now().After(p.expires) {
				s.mu.Unlock()
				w.WriteHeader(http.StatusGone)
				write(map[string]any{"apiVersion": "v1", "kind": "Status", "code": 410, "reason": "Expired", "status": "Failure"})
				return
			}
			items, rev = p.items, p.revision
		}
		for key, p := range s.pages {
			if time.Now().After(p.expires) {
				delete(s.pages, key)
			}
		}
		if token == "" {
			s.Backend.Mu.Lock()
			keys := []string{}
			for k := range s.Backend.Objects {
				if strings.HasPrefix(k, gvr+"/") && (ns == "" || strings.HasPrefix(k, gvr+"/"+ns+"/")) {
					keys = append(keys, k)
				}
			}
			sort.Strings(keys)
			items = make([]any, 0, len(keys))
			for _, k := range keys {
				items = append(items, clone(s.Backend.Objects[k]))
			}
			s.Backend.Mu.Unlock()
		}
		next := ""
		limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
		if limit > 0 && len(items) > limit {
			s.continuation++
			next = fmt.Sprintf("%s-%d-%d", gvr, rev, s.continuation)
			if len(s.pages) >= 128 {
				s.mu.Unlock()
				w.WriteHeader(http.StatusTooManyRequests)
				write(map[string]any{"apiVersion": "v1", "kind": "Status", "code": 429, "reason": "TooManyRequests", "status": "Failure"})
				return
			}
			s.pages[next] = page{items[limit:], rev, time.Now().Add(30 * time.Second)}
			items = items[:limit]
		}
		hold, captured := s.HoldList, s.ListCaptured
		s.mu.Unlock()
		if hold != nil && token == "" {
			if captured != nil {
				select {
				case captured <- struct{}{}:
				default:
				}
			}
			select {
			case <-hold:
			case <-r.Context().Done():
				return
			}
		}
		kind := map[string]string{"vpcs": "VPC", "subnets": "Subnet", "pods": "Pod", "vnics": "VNic", "vnicips": "VNicIP", "eips": "EIP", "snats": "Snat", "nats": "Nat", "eipgateways": "EIPGateway", "vlannetworks": "VlanNetwork", "nodes": "Node", "configmaps": "ConfigMap", "services": "Service", "servicecidrs": "ServiceCIDR"}[gvr]
		version := "networking.kubercloud.com/v1"
		if gvr == "pods" || gvr == "nodes" || gvr == "configmaps" || gvr == "services" {
			version = "v1"
		}
		if items == nil {
			items = []any{}
		}
		write(map[string]any{"apiVersion": version, "kind": kind + "List", "metadata": map[string]any{"resourceVersion": strconv.FormatInt(rev, 10), "continue": next}, "items": items})
		return
	}
	recorder := httptest.NewRecorder()
	s.Backend.ServeHTTP(recorder, r)
	w.WriteHeader(recorder.Code)
	_, _ = w.Write(recorder.Body.Bytes())
	s.mu.Lock()
	s.bytes[key] += int64(recorder.Body.Len())
	s.mu.Unlock()
	if (verb == "POST" && recorder.Code == 201) || (verb == "PATCH" && recorder.Code == 200) {
		var obj map[string]any
		if json.Unmarshal(recorder.Body.Bytes(), &obj) == nil {
			s.Change(gvr, obj, false)
		}
	}
}

func (s *Server) SetListHold(hold <-chan struct{}, captured chan<- struct{}) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.HoldList = hold
	s.ListCaptured = captured
}
func (s *Server) Object(gvr, namespace, name string) map[string]any {
	s.Backend.Mu.Lock()
	defer s.Backend.Mu.Unlock()
	return clone(s.Backend.Objects[gvr+"/"+namespace+"/"+name])
}
