package main

import (
	"log"
	"net/http"
	"os"
	"strings"

	"ollama-exporter/handler"
	"ollama-exporter/ollama"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type ExporterConfig struct {
	OllamaURL  string
	ListenPort string
}

func getEnv(key, fallback string) string {
	if val, ok := os.LookupEnv(key); ok {
		return val
	}

	return fallback
}

func NewExporterConfig(proto, host, port string) *ExporterConfig {
	ollamaProto := getEnv("OLLAMA_PROTO", proto)
	ollamaHost := getEnv("OLLAMA_HOST", host)

	ollamaURL := ollamaProto + "://" + ollamaHost

	tmpPort := getEnv("PROXY_PORT", port)

	var b strings.Builder
	if !strings.ContainsRune(tmpPort, ':') {
		b.WriteRune(':')
	}

	b.WriteString(tmpPort)
	return &ExporterConfig{
		OllamaURL:  ollamaURL,
		ListenPort: b.String(),
	}
}

func (cfg *ExporterConfig) PrintConfig() {
	log.Printf("--------------------------------------------------------------------")
	log.Printf("   [ POST ]  /generate .....  instrumented requests to `OLLAMA_URL` ")
	log.Printf("   [ GET ]   /metrics  .....  prometheus scrape endpoint            ")
	log.Printf("--------------------------------------------------------------------")
	log.Printf("  starting listener:   'localhost%s'", cfg.ListenPort)
	log.Printf("         OLLAMA_URL:   '%s'", cfg.OllamaURL)
	log.Printf("--------------------------------------------------------------------")
	log.Printf("")
}

func main() {

	config := NewExporterConfig("http", "localhost:11434", ":9110")
	client := ollama.NewClient(config.OllamaURL)

	mux := http.NewServeMux()
	mux.HandleFunc("/generate", handler.GenerateHandler(client))
	mux.Handle("/metrics", promhttp.Handler())

	config.PrintConfig()

	log.Fatal(http.ListenAndServe(config.ListenPort, mux))
}
