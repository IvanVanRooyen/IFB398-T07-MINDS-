import os
import requests

class GraniteClient:
    """
    Minimal, backend-only caller. Backends:
      - OLLAMA (default): OLLAMA_URL=http://localhost:11434
                          GRANITE_MODEL=granite3.2:8b-instruct-fp16
      - HF:      HF_INFERENCE_URL=https://api-inference.huggingface.co/models/ibm-granite/...
                 HF_TOKEN=...
    """
    def __init__(self, backend=None):
        self.backend = backend or os.getenv("GRANITE_BACKEND", "ollama").lower()
        self.model = os.getenv("GRANITE_MODEL", "granite3.2:8b-instruct-fp16")
        self.timeout = int(os.getenv("GRANITE_TIMEOUT", "120"))

        if self.backend == "ollama":
            base = os.getenv("OLLAMA_URL", "http://localhost:11434")
            self.url = f"{base}/api/generate"
        elif self.backend == "hf":
            self.url = os.getenv("HF_INFERENCE_URL")
            self.hf_token = os.getenv("HF_TOKEN")
            if not self.url:
                raise RuntimeError("HF_INFERENCE_URL not set")
        else:
            raise ValueError("Unsupported GRANITE_BACKEND")

    def complete(self, prompt: str, max_new_tokens: int = 900):
        if self.backend == "ollama":
            payload = {
                "model": self.model,
                "prompt": prompt,
                "options": {"num_ctx": 8192},
                "stream": False,
            }
            r = requests.post(self.url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")

        headers = {"Authorization": f"Bearer {self.hf_token}"} if getattr(self, "hf_token", None) else {}
        r = requests.post(
            self.url,
            headers=headers,
            json={"inputs": prompt, "parameters": {"max_new_tokens": max_new_tokens}},
            timeout=self.timeout,
        )
        r.raise_for_status()
        out = r.json()
        if isinstance(out, list) and out:
            return out[0].get("generated_text", "")
        return str(out)
