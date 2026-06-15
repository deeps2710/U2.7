# Phase 9: Offline Voice Stack

Phase 9 upgrades ULTRON 2.7 from a browser-only voice prototype to an offline-first voice stack with explicit STT/TTS provider selection and health checks.

The safety model is unchanged:

```text
voice -> STT -> brain/runtime -> typed tool call -> validation -> policy
-> executor -> audit -> response -> TTS
```

Voice providers can only transform audio to text or text to speech. They do not receive raw shell access and cannot bypass tool validation, confirmation, policy, executor restrictions, or audit logging.

## What Changed

- Added local STT adapters for `faster_whisper` and `whisper_cpp`.
- Added local TTS adapters for `piper` and `pyttsx3`.
- Kept browser transcript and browser speech synthesis as fallbacks.
- Added mock STT/TTS providers for deterministic tests.
- Added voice provider configuration fields to `UltronConfig`.
- Added provider health checks and test endpoints.
- Updated the web UI to show configured and active STT/TTS providers.
- Added a Phase 9 launcher: `scripts/run_phase9_voice_ui.py`.

## Run

```powershell
python scripts/run_phase9_voice_ui.py --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

## Configuration

Start with browser fallbacks:

```json
{
  "voice_stt_provider": "browser",
  "voice_tts_provider": "browser_speech_synthesis",
  "voice_stt_model_path": null,
  "voice_tts_model_path": null,
  "voice_tts_voice_path": null,
  "voice_device": "cpu",
  "voice_identity": "ULTRON",
  "voice_rate": 0.92,
  "voice_pitch": 0.72,
  "voice_volume": 0.95
}
```

Example local-first configuration:

```json
{
  "voice_stt_provider": "faster_whisper",
  "voice_tts_provider": "piper",
  "voice_stt_model_path": ".ultron/models/faster-whisper-small",
  "voice_tts_model_path": ".ultron/models/piper/en_US-lessac-medium.onnx",
  "voice_tts_voice_path": ".ultron/models/piper/en_US-lessac-medium.onnx.json",
  "voice_device": "cpu",
  "voice_identity": "ULTRON",
  "voice_rate": 0.92,
  "voice_pitch": 0.72,
  "voice_volume": 0.95
}
```

Environment overrides:

```powershell
$env:ULTRON_STT_PROVIDER = "faster_whisper"
$env:ULTRON_TTS_PROVIDER = "piper"
$env:ULTRON_STT_MODEL_PATH = ".ultron/models/faster-whisper-small"
$env:ULTRON_TTS_MODEL_PATH = ".ultron/models/piper/en_US-lessac-medium.onnx"
$env:ULTRON_TTS_VOICE_PATH = ".ultron/models/piper/en_US-lessac-medium.onnx.json"
$env:ULTRON_VOICE_DEVICE = "cpu"
$env:ULTRON_VOICE_IDENTITY = "ULTRON"
$env:ULTRON_VOICE_RATE = "0.92"
$env:ULTRON_VOICE_PITCH = "0.72"
$env:ULTRON_VOICE_VOLUME = "0.95"
```

## Provider Matrix

| Provider | Type | Local? | Notes |
|---|---|---|---|
| `browser` | STT | no | Uses browser recognition and sends transcript text to the backend. |
| `text_payload` | STT | local test path | Accepts transcript/text JSON payloads for deterministic runs. |
| `faster_whisper` | STT | yes | Requires the `faster-whisper` Python package and a model path. |
| `whisper_cpp` | STT | yes | Requires a whisper.cpp executable on PATH and a model path. |
| `browser_speech_synthesis` | TTS | no | Delegates speech playback to the browser. |
| `piper` | TTS | yes | Requires the Piper executable on PATH and a model path. |
| `pyttsx3` | TTS | yes | Requires the `pyttsx3` Python package. |
| `mock` | STT/TTS | test | Deterministic provider for tests and demos. |

## API

```text
GET  /api/voice/providers
POST /api/voice/test-stt
POST /api/voice/test-tts
```

These endpoints do not execute user commands. They only report provider readiness and exercise the selected STT/TTS path.

Existing voice endpoints remain:

```text
POST /api/voice/start
POST /api/voice/stop
POST /api/voice/transcribe
POST /api/speak
GET  /api/voice/status
```

## Fallback Behavior

If a configured local provider is unavailable, ULTRON records the configured provider as unavailable and activates a fallback:

- missing local STT -> browser transcript fallback,
- missing local TTS -> browser speech synthesis fallback,
- missing TTS playback -> subtitles still show the response,
- missing microphone/STT -> typed command input still works.

This keeps the prototype usable even before local models are installed.
