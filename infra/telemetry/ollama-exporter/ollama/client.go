package ollama

import (
	"bytes"
	"fmt"
	"io"
	"time"

	"encoding/json"
	"net/http"

	"ollama-exporter/metrics"
)

type Client struct {
	baseURL    string
	httpClient *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

func (c *Client) Generate(req GenerateRequest) (*GenerateResponse, error) {
	const endpoint = "/api/generate"

	req.Stream = false

	timer := metrics.NewRequestTimer(req.Model, endpoint)
	defer timer.ObserveDuration()

	body, err := json.Marshal(req)
	if err != nil {
		metrics.RecordRequest(req.Model, endpoint, "error")
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	resp, err := c.httpClient.Post(
		c.baseURL+endpoint,
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		metrics.RecordRequest(req.Model, endpoint, "error")
		return nil, fmt.Errorf("post to ollama: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		metrics.RecordRequest(req.Model, endpoint, "error")
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		metrics.RecordRequest(req.Model, endpoint, "error")
		return nil, fmt.Errorf("ollama returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result GenerateResponse
	if err := json.Unmarshal(respBody, &result); err != nil {
		metrics.RecordRequest(req.Model, endpoint, "error")
		return nil, fmt.Errorf("unmarshal response: %w", err)
	}

	metrics.RecordRequest(req.Model, endpoint, "success")
	metrics.RecordTokens(req.Model, result.EvalCount, result.PromptEvalCount)

	return &result, nil
}
