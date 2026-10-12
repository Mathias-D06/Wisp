"""Spike: print the google-genai Live type fields the app relies on.

Run: .venv\\Scripts\\python spikes\\genai_types.py
Proves field names against the installed SDK instead of memory (see SOURCES.md).
"""

from google.genai import types

NAMES = [
    "LiveConnectConfig",
    "LiveServerMessage",
    "LiveServerContent",
    "LiveServerToolCall",
    "LiveServerToolCallCancellation",
    "LiveServerGoAway",
    "LiveServerSessionResumptionUpdate",
    "SessionResumptionConfig",
    "ContextWindowCompressionConfig",
    "SlidingWindow",
    "RealtimeInputConfig",
    "AutomaticActivityDetection",
    "FunctionDeclaration",
    "FunctionResponse",
    "FunctionCall",
    "Transcription",
    "SpeechConfig",
]

for name in NAMES:
    cls = getattr(types, name)
    print(f"{name}: {', '.join(cls.model_fields)}")

for enum_name in ["ActivityHandling", "TurnCoverage", "StartSensitivity", "EndSensitivity"]:
    print(enum_name, [m.name for m in getattr(types, enum_name)])
