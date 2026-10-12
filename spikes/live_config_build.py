"""Spike: build a LiveConnectConfig with Wisp-style tool schemas and print the wire JSON.

Run: .venv\\Scripts\\python spikes\\live_config_build.py
Proves that lower-case OpenAPI types in dict declarations validate in google-genai 2.29.0 and
shows how the SDK serialises them for the BidiGenerateContent setup message.
"""

import json

from google.genai import _live_converters, types

declaration = {
    "name": "open_app",
    "description": "Open an app",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "app name"},
            "count": {"type": "integer", "description": "n"},
            "where": {"type": "string", "enum": ["google", "youtube"], "description": "site"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "tool": {"type": "string", "description": "tool"}}}, "description": "steps"},
        },
        "required": ["name"],
    },
}

config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
        )
    ),
    system_instruction="You are Wisp.",
    tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**declaration)])],
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    context_window_compression=types.ContextWindowCompressionConfig(
        sliding_window=types.SlidingWindow()
    ),
    session_resumption=types.SessionResumptionConfig(handle=None),
    realtime_input_config=types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
    ),
)
fd = config.tools[0].function_declarations[0]
print("parameter type parsed as:", repr(fd.parameters.type))
parent: dict = {}
_live_converters._LiveConnectConfig_to_mldev(
    api_client=None, from_object=config.model_dump(exclude_none=True), parent_object=parent
)
print(json.dumps(parent, indent=1, default=str)[:3000])
