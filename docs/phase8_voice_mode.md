# Phase 8: Voice Mode

Phase 8 adds voice interaction to the Phase 7 visual interface while preserving ULTRON's safety model. Voice input becomes another adapter into the same brain/runtime pipeline; it does not receive shell access or executor authority.

## What Changed

- Added `src/ultron27/voice.py`.
- Added voice state, transcript history, STT and TTS provider abstractions.
- Added a browser speech-recognition path for microphone capture on supported browsers.
- Added browser speech synthesis for ULTRON's audible response, with backend `/api/speak` state tracking.
- Added UI controls for microphone on/off, push-to-talk, mute, stop voice, explicit confirmation, and mock voice.
- Added voice API endpoints to `src/ultron27/web_server.py`.
- Added Phase 8 regression tests with mocked STT/TTS behavior.
- Added `scripts/run_phase8_voice_ui.py` as a Phase 8-named launcher.

## How To Run

```powershell
python scripts/run_phase8_voice_ui.py --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The older launcher still works because the same web server now includes both Phase 7 visuals and Phase 8 voice controls:

```powershell
python scripts/run_phase7_ui.py --port 8765
```

## Voice Flow

```text
voice -> browser speech recognition -> /api/voice/transcribe
-> brain/runtime -> typed tool call -> validation -> policy -> executor
-> audit -> response text -> /api/speak -> browser speech synthesis
```

If browser speech recognition is unavailable, typed commands and the Mock Voice button remain available.

## Voice Activity Detection

For this phase, voice activity detection is lightweight:

- the browser speech-recognition adapter reports start, speech-start, speech-end, and end events;
- the sphere enters listening while the browser is waiting for speech;
- empty transcripts are rejected by the backend and do not execute commands;
- noisy or unavailable microphone paths fall back to typed commands and Mock Voice.

## API Endpoints

```text
POST /api/voice/start
POST /api/voice/stop
POST /api/voice/transcribe
POST /api/speak
GET  /api/voice/status
```

Existing Phase 7 endpoints remain available:

```text
POST /api/command
GET  /api/status
GET  /api/memory
POST /api/subtitles/toggle
POST /api/state
```

## Voice Controls

- Mic On/Off toggles browser speech recognition when supported.
- Push-to-talk switches between one-shot and continuous recognition behavior.
- Mute Off/Muted controls whether ULTRON speaks aloud.
- Stop Voice cancels current browser speech synthesis.
- Confirm sends the explicit confirmation phrase for pending high-risk actions.
- Mock Voice sends a deterministic sample command through the voice pipeline.

## Safety Behavior

High-risk voice commands pause exactly like typed commands. ULTRON asks for explicit confirmation and records the pending goal. The confirmation phrase is:

```text
yes confirm
```

Even after confirmation, destructive actions remain dry-run or not implemented unless a safe executor has been intentionally designed.

## Provider Strategy

The current implementation uses:

- `TextPayloadSTT` for deterministic backend transcript intake,
- browser speech recognition as the local UI capture adapter when available,
- `BrowserSpeechTTS` to delegate actual audio output to browser speech synthesis,
- `MockTTS` for deterministic tests.

This keeps Phase 8 lightweight and working now, while leaving a clean provider seam for faster-whisper, whisper.cpp, Piper, or pyttsx3 later.
