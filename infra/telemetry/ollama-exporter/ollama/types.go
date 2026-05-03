package ollama

type GenerateRequest struct {
	Model  string `json:"model"`
	Prompt string `json:"prompt"`
	Stream bool   `json:"stream"`
}

type GenerateResponse struct {
	Model           string `json:"model"`
	Response        string `json:"response"`
	Done            bool   `json:"done"`
	TotalDuration   int64  `json:"total_duration"`
	LoadDuration    int64  `json:"load_duration"`
	EvalCount       int    `json:"eval_count"`
	EvalDuration    int    `json:"eval_duration"`
	PromptEvalCount int    `json:"prompt_eval_count"`
}
