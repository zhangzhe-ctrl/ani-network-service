package server

import (
	"github.com/prometheus/client_golang/prometheus"
	"strings"
)

// ObservationMetrics keeps observer health independent of API/DB readiness.
type ObservationMetrics interface{ Snapshot() map[string]float64 }
type observationCollector struct{ source ObservationMetrics }

func (c observationCollector) Describe(ch chan<- *prometheus.Desc) { /* dynamic fixed metric set: unchecked collector */
}
func (c observationCollector) Collect(ch chan<- prometheus.Metric) {
	for name, value := range c.source.Snapshot() {
		kind := prometheus.GaugeValue
		if strings.HasSuffix(name, "_total") {
			kind = prometheus.CounterValue
		}
		ch <- prometheus.MustNewConstMetric(prometheus.NewDesc("ani_network_observation_"+name, "Shared observation runtime measurement.", nil, nil), kind, value)
	}
}
func (o *Observability) RegisterObservation(source ObservationMetrics) error {
	return o.registry.Register(observationCollector{source})
}
