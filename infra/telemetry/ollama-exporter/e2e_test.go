package main

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	dto "github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"

	"ollama-exporter/handler"
	"ollama-exporter/ollama"
)

// Wires in a way similar to the `main` func; backed by a mock ollama server instead.
// Returns the app server and mock backend, with both intended to be closed by the caller.
func buildStack(t *testing.T) (appServer *httptest.Server, ollamaBackend *httptest.Server) {
	t.Helper()

	ollamaBackend = httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			var req ollama.GenerateRequest
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, "bad request", http.StatusBadRequest)
				return
			}

			resp := ollama.GenerateResponse{
				Model:           req.Model,
				Response:        "Integration test reply for: " + req.Prompt,
				Done:            true,
				EvalCount:       12,
				PromptEvalCount: 5,
				TotalDuration:   150_000_000, // nanoseconds = 150ms
			}
			json.NewEncoder(w).Encode(resp)
		},
	))

	// real application stack connected to the mock backend
	client := ollama.NewClient(ollamaBackend.URL)

	mux := http.NewServeMux()
	mux.HandleFunc("/generate", handler.GenerateHandler(client))
	mux.Handle("/metrics", promhttp.Handler())

	appServer = httptest.NewServer(mux)
	return appServer, ollamaBackend
}

// Fetches `/metrics` from the application and parses the into a map.
// The returned map is keyed by metric name.
func scrapeMetrics(t *testing.T, appURL string) map[string]*dto.MetricFamily {
	t.Helper()

	resp, err := http.Get(appURL + "/metrics")
	if err != nil {
		t.Fatalf("failed to fetch: /metrics: %v", err)
	}
	defer resp.Body.Close()

	// Determine wire format from `content-type` header
	format := expfmt.ResponseFormat(resp.Header)

	families := make(map[string]*dto.MetricFamily)
	decoder := expfmt.NewDecoder(resp.Body, format)
	for {
		var mf dto.MetricFamily
		if err := decoder.Decode(&mf); err != nil {
			if err == io.EOF {
				break
			}
			t.Fatalf("failed during metric family decode: %v", err)
		}
		families[mf.GetName()] = &mf
	}
	
	return families
}

func matchLabels(m *dto.Metric, wants map[string]string) bool {
	have := make(map[string]string)
	for _, lp := range m.GetLabel() {
		have[lp.GetName()] = lp.GetValue()
	}

	for k, v := range wants {
		if have[k] != v {
			return false
		}
	}

	return true
}

// Retrieves a counter value matching a given label
func findCounter(family *dto.MetricFamily, labels map[string]string) float64 {
	for _, m := range family.GetMetric() {
		if matchLabels(m, labels) {
			return m.GetCounter().GetValue()
		}
	}

	return 0
}

// Retrieves the sample count from a histogram matching the given labels
func findHistogramCount(family *dto.MetricFamily, labels map[string]string) uint64 {
	for _, m := range family.GetMetric() {
		if matchLabels(m, labels) {
			return m.GetHistogram().GetSampleCount()
		}
	}

	return 0
}

func TestE2E_SuccessfulGenerate(t *testing.T) {
	app, backend := buildStack(t)
	defer app.Close()
	defer backend.Close()

	body := `{"model":"granite4:350m","prompt":"hello ollama"}`
	resp, err := http.Post(app.URL+"/generate", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatalf("request fail: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(resp.Body)
		t.Fatalf("status = %d, body = %s", resp.StatusCode, string(raw))
	}

	var genResp ollama.GenerateResponse
	if err := json.NewDecoder(resp.Body).Decode(&genResp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if genResp.Model != "granite4:350m" {
		t.Errorf("model = %q, wanted granite4:350m", genResp.Model)
	}

	if !strings.Contains(genResp.Response, "hello ollama") {
		t.Errorf("response should echo the prompt, got %q", genResp.Response)
	}

	if genResp.EvalCount != 12 {
		t.Errorf("eval_count = %d, wanted 12", genResp.EvalCount)
	}

	metrics := scrapeMetrics(t, app.URL)

	// request counter - should have at least 1 success
	reqFamily := metrics["ollama_requests_total"]
	if reqFamily == nil {
		t.Fatal("missing metric: 'ollama_requests_total'")
	}

	successCount := findCounter(reqFamily, map[string]string{
		"model": "granite4:350m", "endpoint": "/api/generate", "status": "success",
	})
	if successCount < 1 {
		t.Errorf("expected at least 1 successful request, got %f", successCount)
	}

	// duration hist - should have at least 1 observation
	durFamily := metrics["ollama_request_duration_seconds"]
	if durFamily == nil {
		t.Fatal("missing metric: 'ollama_request_duration_seconds'")
	}

	durCount := findHistogramCount(durFamily, map[string]string{
		"model": "granite4:350m", "endpoint": "/api/generate",
	})
	if durCount < 1 {
		t.Errorf("expected at least 1 successful observation, got %f", successCount)
	}

	// token counter - should reflect the fake response
	evalFamily := metrics["ollama_tokens_generated_total"]
	if evalFamily == nil {
		t.Fatal("missing metric: 'ollama_tokens_generated_total'")
	}

	evalTokens := findCounter(evalFamily, map[string]string{"model": "granite4:350m"})
	if evalTokens < 12 {
		t.Errorf("expected at least 12 generated tokens, got %f", evalTokens)
	}

	promptFamily := metrics["ollama_tokens_prompt_total"]
	if promptFamily == nil {
		t.Fatal("missing metric: 'ollama_tokens_prompt_total'")
	}

	promptTokens := findCounter(promptFamily, map[string]string{"model": "granite4:350m"})
	if promptTokens < 5 {
		t.Errorf("expected at least 5 prompt tokens, got %f", promptTokens)
	}
}

func TestE2E_OllamaDown(t *testing.T) {
	app, backend := buildStack(t)
	backend.Close()

	body := `{"model":"granite4:350m","prompt":"should fail"}`
	resp, err := http.Post(app.URL+"/generate", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatalf("request to app failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadGateway {
		t.Errorf("status = %d, want 502", resp.StatusCode)
	}

	metrics := scrapeMetrics(t, app.URL)
	reqFamily := metrics["ollama_requests_total"]
	if reqFamily != nil {
		errCount := findCounter(reqFamily, map[string]string{
			"model": "granite4:350m", "status": "error",
		})
		if errCount < 1 {
			t.Errorf("expected error count >= 1, got %f", errCount)
		}
	}

	app.Close()
}
