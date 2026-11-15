"""Ollama first, with FreeLLMAPI for complex questions and service failures."""
import os
import re

import requests
from openai import OpenAI
from jarvis.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, SYSTEM_PROMPT


class Brain:
    def __init__(self):
        self.client = OpenAI(
            base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "not-configured",
            timeout=30.0, max_retries=0,
        )
        self.ollama_url = os.getenv("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.ollama_model = os.getenv("JARVIS_OLLAMA_MODEL", "qwen3.5:2b")
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_backend = None

    @staticmethod
    def _route(text):
        # Simple, inspectable rules; this does not measure question difficulty.
        for prefix, backend in (("use local", "local"), ("use cloud", "cloud")):
            match = re.match(r"^" + prefix + r"\b[\s,:-]*", text, re.I)
            if match:
                return backend, text[match.end():].strip(), True
        complex_request = re.search(
            r"\b(debug|debugging|refactor|algorithm|algorithms|proof|prove|"
            r"calculus|integral|derivative|research|in.depth|step.by.step)\b|```|"
            r"\b(write|generate|implement|fix|review)\b.{0,60}\b(code|program|function|script)\b",
            text, re.I,
        )
        return ("cloud" if complex_request or len(text) > 700 else "local"), text, False

    @staticmethod
    def _answer_text(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Empty model response")
        return value.strip()

    def _local(self, messages):
        response = requests.post(
            self.ollama_url + "/api/chat",
            json={"model": self.ollama_model, "messages": messages,
                  "stream": False, "think": False, "keep_alive": "5m",
                  "options": {"num_predict": 250, "num_ctx": 4096, "temperature": 0.7}},
            timeout=(5, 60),
        )
        response.raise_for_status()
        return self._answer_text(response.json()["message"]["content"])

    def _cloud(self, messages):
        if not LLM_API_KEY:
            raise RuntimeError("Set JARVIS_CLOUD_API_KEY to enable cloud requests")
        response = self.client.chat.completions.create(
            model=LLM_MODEL, messages=messages, max_tokens=250, temperature=0.7,
        )
        return self._answer_text(response.choices[0].message.content)

    def think(self, user_text):
        backend, text, explicit = self._route(user_text.strip())
        self.last_backend = None
        if not text:
            return "Please include a question after use local or use cloud, sir."
        # Keep complete user/assistant pairs, with the system prompt intact.
        previous = [self.history[0]] + self.history[1:][-8:]
        messages = previous + [{"role": "user", "content": text}]
        # An explicit local request never leaves the machine if Ollama fails.
        attempts = [backend] if explicit else [backend, "cloud" if backend == "local" else "local"]
        for selected in attempts:
            print(f"[Brain] Using {selected} ({self.ollama_model if selected == 'local' else LLM_MODEL})")
            try:
                answer = self._local(messages) if selected == "local" else self._cloud(messages)
                self.history = messages + [{"role": "assistant", "content": answer}]
                self.last_backend = selected
                return answer
            except Exception as error:
                # Exception messages can include credentials or prompt content.
                print(f"[Brain] {selected} unavailable ({type(error).__name__})")
        return "I couldn't reach the requested AI service, sir. Please check Ollama or FreeLLMAPI and try again."
