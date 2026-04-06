package ollama

import (
	"testing"

	"encoding/json"
	"net/http"
	"net/http/httptest"
)

// Returns a mock Ollama server with an `/api/generate` endpoint using *httptest.Server
func fakeOllamaServer(t *testing.T, statusCode int, res GenerateResponse) *httptest.Server {
	t.Helper()

	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}

		if r.URL.Path != "/api/generate" {
			t.Errorf("expected /api/generate, got %s", r.URL.Path)
		}

		var req GenerateRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("failed to decode request body: %v", err)
		}

		if req.Stream {
			t.Error("expected stream=false (was true) - client should force this off")
		}

		w.WriteHeader(statusCode)
		json.NewEncoder(w).Encode(res)
	}))
}

func TestGenerate_Success(t *testing.T) {
	want := GenerateResponse{
		Model:           "granite4:350m",
		Response:        "hello, world!",
		Done:            true,
		EvalCount:       5,
		PromptEvalCount: 3,
	}

	server := fakeOllamaServer(t, http.StatusOK, want)
	defer server.Close()

	client := NewClient(server.URL)
	got, err := client.Generate(GenerateRequest{
		Model:  "granite4:350m",
		Prompt: "say hello",
	})

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got.Response != want.Response {
		t.Fatalf("response = %q, wanted %q", got.Response, want.Response)
	}

	if got.EvalCount != want.EvalCount {
		t.Errorf("eval_count = %d, wanted %d", got.EvalCount, want.EvalCount)
	}

	if got.PromptEvalCount != want.PromptEvalCount {
		t.Errorf(
			"prompt_eval_count = %d, wanted %d",
			got.PromptEvalCount,
			want.PromptEvalCount,
		)
	}
}

func TestGenerate_OllamaError(t *testing.T) {
	server := fakeOllamaServer(t, http.StatusInternalServerError, GenerateResponse{})
	defer server.Close()

	client := NewClient(server.URL)
	_, err := client.Generate(GenerateRequest{
		Model:  "granite4:350m",
		Prompt: "should fail",
	})

	if err == nil {
		t.Fatal("expected error for 500, got nil")
	}
}

func TestGenerate_ConnectionRefused(t *testing.T) {
	// pointed to port that SHOULD have nothing else listening...
	client := NewClient("http://localhost:19999")
	_, err := client.Generate(GenerateRequest{
		Model:  "granite4:350m",
		Prompt: "wont connect",
	})

	if err == nil {
		t.Fatal("expected connection error, got nil")
	}
}
