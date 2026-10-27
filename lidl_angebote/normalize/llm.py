"""Minimaler Ollama-Client (nur Standardbibliothek)."""

import json
import urllib.error
import urllib.request

SCHEMA = {
    "type": "object",
    "properties": {"texts": {"type": "array", "items": {"type": "string"}}},
    "required": ["texts"],
}


class OllamaError(RuntimeError):
    pass


class Ollama:
    def __init__(self, url="http://127.0.0.1:11434", model="qwen3.5:2b", timeout=900):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout

    def _post(self, path, payload):
        request = urllib.request.Request(
            self.url + path, json.dumps(payload).encode(), {"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            raise OllamaError(f"Ollama ({self.url}) nicht nutzbar: {e}") from e

    def available(self):
        """True, wenn der Server antwortet und das Modell geladen werden kann."""
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=10) as response:
                names = {m["name"] for m in json.load(response)["models"]}
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, KeyError):
            return False
        return self.model in names or f"{self.model}:latest" in names

    def correct(self, system, texts):
        """Korrigierte Texte in gleicher Reihenfolge; die Länge prüft der Aufrufer."""
        reply = self._post(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "think": False,  # Qwen 3.5 „denkt“ sonst erst minutenlang; auf der CPU unbezahlbar
                "format": SCHEMA,
                "options": {"temperature": 0, "num_ctx": 4096},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps({"texts": texts}, ensure_ascii=False)},
                ],
            },
        )
        try:
            result = json.loads(reply["message"]["content"])["texts"]
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            raise OllamaError(f"Unerwartete Antwort von Ollama: {e}") from e
        return [t if isinstance(t, str) else "" for t in result]
