"""Minimaler Ollama-Client (nur Standardbibliothek)."""

import json
import urllib.error
import urllib.request

TYPO_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "wort": {"type": "string"}, "korrekt": {"type": "string"}},
                "required": ["id", "wort", "korrekt"],
            },
        }
    },
    "required": ["fixes"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"wahl": {"type": "string", "enum": ["a", "b"]}, "grund": {"type": "string"}},
    "required": ["wahl", "grund"],
}


class OllamaError(RuntimeError):
    pass


class Ollama:
    def __init__(self, url="http://127.0.0.1:11434", model="gemma4:e4b", timeout=900):
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

    def typos(self, system, texts):
        """Gemeldete Tippfehler als ``[{"id": 1-basiert, "wort", "korrekt"}]``; nur Korrekturen, nie ganze Texte."""
        numbered = "\n".join(f"{n}: {text}" for n, text in enumerate(texts, 1))
        reply = self._post(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "think": False,
                "format": TYPO_SCHEMA,
                "options": {"temperature": 0, "num_ctx": 2048},  # Prompt + 16 Texte passen; mehr Kontext kostet nur Speicher
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": numbered}],
            },
        )
        try:
            fixes = json.loads(reply["message"]["content"])["fixes"]
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            raise OllamaError(f"Unerwartete Antwort von Ollama: {e}") from e
        return [
            f
            for f in fixes
            if isinstance(f, dict)
            and isinstance(f.get("id"), int)
            and 1 <= f["id"] <= len(texts)
            and isinstance(f.get("wort"), str)
            and isinstance(f.get("korrekt"), str)
        ]

    def judge(self, system, payload):
        """Zweitmeinung mit aktiviertem Thinking: ``"a"``, ``"b"`` oder ``None`` (keine verwertbare Antwort)."""
        reply = self._post(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "think": True,
                "format": JUDGE_SCHEMA,
                "options": {"temperature": 0.6, "seed": 0, "num_ctx": 8192, "num_predict": 4000},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        try:
            return json.loads(reply["message"]["content"]).get("wahl")
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError):
            return None  # z. B. Thinking hat das Token-Limit aufgebraucht
