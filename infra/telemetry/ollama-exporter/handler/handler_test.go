package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"ollama-exporter/ollama"
)

// Mock Ollama backend and associated handler
func setupTestHandler(t *testing.T) (http.HandlerFunc, *httptest.Server) {
	t.Helper()

	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		res := ollama.GenerateResponse{
			Model:     "granite4:350m",
			Response:  "test response",
			Done:      true,
			EvalCount: 7,
		}

		json.NewEncoder(w).Encode(res)
	}))

	client := ollama.NewClient(backend.URL)
	return GenerateHandler(client), backend
}

func TestGeneratHandler_Success(t *testing.T) {
	handler, backend := setupTestHandler(t)
	defer backend.Close()

	body := `{"model":"granite4:350m","prompt":"hello"}`
	req := httptest.NewRequest(http.MethodPost, "/generate", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, expected 200", rec.Code)
	}

	var resp ollama.GenerateResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp.Response != "test response" {
		t.Errorf("response = %q, expected %q", resp.Response, "test response")
	}
}

func TestGenerateHandler_MissingFields(t *testing.T) {
	handler, backend := setupTestHandler(t)
	defer backend.Close()

	tests := []struct {
		name string
		body string
	}{
		{"missing model", `{"prompt":"hello'}`},
		{"missing prompt", `{"model":"granite4:350m"}`},
		{"missing both", `{}`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, "/generate", strings.NewReader(tt.body))
			rec := httptest.NewRecorder()

			handler(rec, req)

			if rec.Code != http.StatusBadRequest {
				t.Errorf("status = %d, expected 400", rec.Code)
			}
		})
	}
}
