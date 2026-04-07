package metrics

import (
	"log"

	"github.com/prometheus/client_golang/prometheus"
)

var (
	requestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ollama_requests_total",
			Help: "Total number of requests to Ollama by model, endpoint, and status.",
		},
		[]string{"model", "endpoint", "status"},
	)

	requestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name: "ollama_request_duration_seconds",
			Help: "Latency of Ollama API requests in seconds.",

			// Buckets: prometheus.ExponentialBuckets(0.1, 2, 10),
			Buckets: prometheus.LinearBuckets(5, 5, 10),
		},
		[]string{"model", "endpoint"},
	)

	tokensGenerated = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ollama_tokens_generated_total",
			Help: "Cumulative completion tokens produced by Ollama.",
		},
		[]string{"model"},
	)

	tokensPrompt = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ollama_tokens_prompt_total",
			Help: "Cumulative prompt/input tokens evaluated by Ollama.",
		},
		[]string{"model"},
	)

	activeRequests = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "ollama_active_requests",
			Help: "Number of in-flight requests to Ollama.",
		},
	)
)

func init() {
	log.Printf("startup - register prom init...")
	prometheus.MustRegister(
		requestsTotal,
		requestDuration,
		tokensGenerated,
		tokensPrompt,
		activeRequests,
	)
}

func NewRequestTimer(model, endpoint string) *prometheus.Timer {
	log.Printf("[meter] recv: NewRequestTimer")

	activeRequests.Inc()
	return prometheus.NewTimer(prometheus.ObserverFunc(func(v float64) {
		requestDuration.WithLabelValues(model, endpoint).Observe(v)
		activeRequests.Dec()
	}))
}

func RecordRequest(model, endpoint, status string) {
	log.Printf("[meter] recv: RecordRequest")

	requestsTotal.WithLabelValues(model, endpoint, status).Inc()
}

func RecordTokens(model string, eval, promptEval int) {
	log.Printf("[meter] recv: RecordTokens")

	tokensGenerated.WithLabelValues(model).Add(float64(eval))
	tokensPrompt.WithLabelValues(model).Add(float64(promptEval))
}
