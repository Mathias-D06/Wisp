"""A loopback stand-in for the Gemini REST API's ``generateContent`` (D-054), so ``--self-check``
and the tests can drive the real google-genai client (and its HTTP stack) without Google: a
``genai.Client`` built by ``client()`` sends to ``http://127.0.0.1:<port>`` instead.

Each request is recorded (path, headers, JSON body). Text models answer ``text``; a model whose
name ends in ``-tts`` answers ``pcm`` as 24 kHz L16 audio, the shape Gemini TTS returns
(ai.google.dev/gemini-api/docs/speech-generation).
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class GeminiLoopback:
    def __init__(self, text: str = "Loopback answer.", pcm: bytes = b"\x00\x00" * 240) -> None:
        self.text = text
        self.pcm = pcm
        self.requests: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # http.server's method name
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append({"path": self.path, "headers": dict(self.headers),
                                       "body": body})
                payload = json.dumps(owner.response(self.path)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args) -> None:  # keep stderr quiet
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="gemini-loopback", daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/"

    def response(self, path: str) -> dict:
        if ":generateContent" not in path:
            return {}
        if path.split(":")[0].endswith("-tts"):
            part = {"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                   "data": base64.b64encode(self.pcm).decode()}}
        else:
            part = {"text": self.text}
        return {"candidates": [{"content": {"role": "model", "parts": [part]},
                                "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 20,
                                  "thoughtsTokenCount": 5, "totalTokenCount": 325}}

    def client(self, api_key: str):
        """A real ``genai.Client`` that talks to this server."""
        from google import genai
        from google.genai import types

        return genai.Client(api_key=api_key,
                            http_options=types.HttpOptions(base_url=self.base_url))

    def __enter__(self) -> GeminiLoopback:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
