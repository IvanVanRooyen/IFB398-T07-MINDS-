package metrics

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
)

// Helper function to extract the current value of a counter from a `CounterVec`.
func counterValue(cv *prometheus.CounterVec, labels ...string) float64 {
	var m dto.Metric
	cv.WithLabelValues(labels...).Write(&m)

	return m.GetCounter().GetValue()
}

// Helper function to the value of a gauge.
func gaugeValue(g prometheus.Gauge) float64 {
	var m dto.Metric
	g.Write(&m)

	return m.GetGauge().GetValue()
}

func TestRecordRequest(t *testing.T) {
	tests := []struct {
		name     string
		model    string
		endpoint string
		status   string
	}{
		{"success case", "granite4:350m", "/api/generate", "success"},
		{"error case", "somemodel:7b", "/api/generate", "error"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			before := counterValue(requestsTotal, tt.model, tt.endpoint, tt.status)
			RecordRequest(tt.model, tt.endpoint, tt.status)
			after := counterValue(requestsTotal, tt.model, tt.endpoint, tt.status)

			if after-before != 1 {
				t.Errorf("expected counter to increment by 1, got %f", after-before)
			}
		})
	}
}

func TestRecordTokens(t *testing.T) {
	model := "granite4:350m"
	evalBefore := counterValue(tokensGenerated, model)
	promptBefore := counterValue(tokensPrompt, model)

	RecordTokens(model, 42, 10)

	evalAfter := counterValue(tokensGenerated, model)
	promptAfter := counterValue(tokensPrompt, model)

	if diff := evalAfter - evalBefore; diff != 42 {
		t.Errorf("tokensGenerated: expected +42, got +%f", diff)
	}

	if diff := promptAfter - promptBefore; diff != 10 {
		t.Errorf("tokensPrompt: expected +10, got %f", diff)
	}
}

func TestNewRequestTimer(t *testing.T) {
	before := gaugeValue(activeRequests)
	timer := NewRequestTimer("granite4:350m", "/api/generate")

	during := gaugeValue(activeRequests)
	if during-before != 1 {
		t.Errorf("active requests should increment by 1 during timing, got %f", during-before)
	}

	timer.ObserveDuration()

	after := gaugeValue(activeRequests)
	if after != before {
		t.Errorf("active requests should return to %f after timer stops, got %f", before, after)
	}
}
