package handler

import (
	"encoding/json"
	"log"
	"net/http"

	"ollama-exporter/ollama"
)

// Returns an http.HandlerFunc to proxy generation requests, facilitating
// instrumentation of the Ollama client.
func GenerateHandler(client *ollama.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		log.Printf("-> %s: %s", r.Method, r.RequestURI)

		if r.Method != http.MethodPost {
			log.Println("method invalid")
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req ollama.GenerateRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			log.Print("invalid body (decode failure)")
			http.Error(w, "invalid request body", http.StatusBadRequest)
			return
		}

		if req.Model == "" || req.Prompt == "" {
			log.Printf(
				`invalid body: '{"model":"%s","prompt":"%s"}'`,
				req.Model,
				req.Prompt,
			)

			http.Error(w, `"model" and "prompt" fields required`, http.StatusBadRequest)
			return
		}

		log.Printf(`proxying generate req: '{"model":"%s","prompt":"%s"}'`, req.Model, req.Prompt)

		resp, err := client.Generate(req)
		if err != nil {
			log.Print("proxying fail:")
			log.Printf("%v", err)
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}
}
