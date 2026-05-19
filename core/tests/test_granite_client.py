"""
Note: does not test huggingface branch functionality.
"""

from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

MODULE_PATH = "core.ai.granite_client"

from core.ai.granite_client import GraniteClient  # noqa: E402

# reusable patch target for requests.post
REQUESTS_POST = f"{MODULE_PATH}.requests.post"


def _mock_response(json_data, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.HTTPError("boom")
    return resp


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class GraniteClientInitTests(SimpleTestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_defaults_to_ollama_backend(self):
        client = GraniteClient()
        self.assertEqual(client.backend, "ollama")
        self.assertEqual(client.model, "granite3.2:8b-instruct-fp16")
        self.assertEqual(client.timeout, 120)
        self.assertEqual(client.url, "http://localhost:11434/api/generate")

    @patch.dict("os.environ", {"OLLAMA_URL": "http://ollama.internal:9999"}, clear=True)
    def test_ollama_url_from_env(self):
        client = GraniteClient()
        self.assertEqual(client.url, "http://ollama.internal:9999/api/generate")

    @patch.dict("os.environ", {"GRANITE_MODEL": "granite3.2:2b-instruct"}, clear=True)
    def test_model_from_env(self):
        client = GraniteClient()
        self.assertEqual(client.model, "granite3.2:2b-instruct")

    @patch.dict("os.environ", {"GRANITE_TIMEOUT": "45"}, clear=True)
    def test_timeout_from_env(self):
        client = GraniteClient()
        self.assertEqual(client.timeout, 45)
        self.assertIsInstance(client.timeout, int)

    @patch.dict("os.environ", {"GRANITE_BACKEND": "OLLAMA"}, clear=True)
    def test_backend_env_is_lowercased(self):
        client = GraniteClient()
        self.assertEqual(client.backend, "ollama")

    @patch.dict("os.environ", {"GRANITE_BACKEND": "ollama"}, clear=True)
    def test_explicit_backend_arg_overrides_env(self):
        # env says ollama, but explicit arg should win
        with patch.dict(
            "os.environ",
            {"HF_INFERENCE_URL": "https://hf.example/model"},
        ):
            client = GraniteClient(backend="hf")
        self.assertEqual(client.backend, "hf")

    @patch.dict(
        "os.environ",
        {
            "HF_INFERENCE_URL": "https://api-inference.huggingface.co/models/ibm-granite/x",
            "HF_TOKEN": "tok-abc",
        },
        clear=True,
    )
    def test_hf_backend_configuration(self):
        client = GraniteClient(backend="hf")
        self.assertEqual(client.backend, "hf")
        self.assertEqual(
            client.url,
            "https://api-inference.huggingface.co/models/ibm-granite/x",
        )
        self.assertEqual(client.hf_token, "tok-abc")

    @patch.dict("os.environ", {"GRANITE_BACKEND": "hf"}, clear=True)
    def test_hf_backend_without_url_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            GraniteClient()
        self.assertIn("HF_INFERENCE_URL", str(ctx.exception))

    @patch.dict(
        "os.environ",
        {"HF_INFERENCE_URL": "https://hf.example/model"},
        clear=True,
    )
    def test_hf_backend_without_token_still_initializes(self):
        client = GraniteClient(backend="hf")
        self.assertIsNone(client.hf_token)

    @patch.dict("os.environ", {"GRANITE_BACKEND": "totally-fake"}, clear=True)
    def test_unsupported_backend_raises(self):
        with self.assertRaises(ValueError):
            GraniteClient()


# ---------------------------------------------------------------------------
# complete() (Local/Ollama branch)
# ---------------------------------------------------------------------------
class GraniteClientCompleteOllamaTests(SimpleTestCase):
    def setUp(self):
        self.env_patcher = patch.dict("os.environ", {}, clear=True)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        self.client = GraniteClient(backend="ollama")

    @patch(REQUESTS_POST)
    def test_returns_response_text_on_success(self, mock_post):
        mock_post.return_value = _mock_response({"response": "Hello there!"})

        result = self.client.complete("Say hi")

        self.assertEqual(result, "Hello there!")

    @patch(REQUESTS_POST)
    def test_posts_to_ollama_generate_endpoint(self, mock_post):
        mock_post.return_value = _mock_response({"response": "x"})

        self.client.complete("prompt")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://localhost:11434/api/generate")

    @patch(REQUESTS_POST)
    def test_payload_contains_required_fields(self, mock_post):
        mock_post.return_value = _mock_response({"response": "x"})

        self.client.complete("the prompt")

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "granite3.2:8b-instruct-fp16")
        self.assertEqual(payload["prompt"], "the prompt")
        self.assertEqual(payload["options"], {"num_ctx": 8192})
        self.assertFalse(payload["stream"])

    @patch(REQUESTS_POST)
    def test_uses_configured_timeout(self, mock_post):
        mock_post.return_value = _mock_response({"response": "x"})

        self.client.complete("prompt")

        self.assertEqual(mock_post.call_args.kwargs["timeout"], 120)

    @patch(REQUESTS_POST)
    def test_returns_empty_string_when_response_key_missing(self, mock_post):
        mock_post.return_value = _mock_response({"unexpected": "shape"})

        result = self.client.complete("prompt")

        self.assertEqual(result, "")

    @patch(REQUESTS_POST)
    def test_http_error_propagates(self, mock_post):
        mock_post.return_value = _mock_response({}, status_ok=False)

        with self.assertRaises(requests.HTTPError):
            self.client.complete("prompt")

    @patch(REQUESTS_POST)
    def test_connection_error_propagates(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("refused")

        with self.assertRaises(requests.ConnectionError):
            self.client.complete("prompt")
