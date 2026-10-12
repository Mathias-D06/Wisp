"""Microphone capture, speaker playback, routing and resampling."""

INPUT_RATE = 16000
"""Live API input: 16-bit PCM mono, 16 kHz, little-endian (ai.google.dev/gemini-api/docs/live)."""

OUTPUT_RATE = 24000
"""Live API output: 16-bit PCM mono, 24 kHz, little-endian."""

INPUT_MIME = "audio/pcm;rate=16000"
