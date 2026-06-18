# Phase 10: Wake Word and Voice Activity Detection

Phase 10 adds natural listening gates to ULTRON 2.7. Wake-word detection and voice activity detection decide whether a candidate speech segment should be sent to STT and the brain.

They do not execute tasks directly.

```text
candidate audio/text -> wake word -> VAD -> STT -> brain/runtime
-> typed tool call -> validation -> policy -> executor -> audit
```

## What Changed

- Added `src/ultron27/wake.py`.
- Added wake-word provider abstraction.
- Added VAD provider abstraction.
- Added always-listening mode to `VoiceSession`.
- Added wake status to voice snapshots.
- Added UI indicators for microphone, wake state, VAD state, and ignored noisy input.
- Added privacy controls: always-listening on/off and push-to-talk remains available.
- Added wake API endpoints.
- Added Phase 10 tests for wake gating, noisy input, VAD-gated STT, and unchanged safety behavior.

## Run

```powershell
python scripts/run_phase10_wake_ui.py --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

## Always-Listening States

```text
inactive
waiting_for_wake_word
listening
transcribing
thinking
speaking
```

The default behavior is privacy-conscious:

- always-listening is off by default,
- push-to-talk remains available,
- microphone status is always visible,
- random background speech is ignored while waiting for the wake phrase,
- empty or noisy input is ignored before STT.

## Wake Phrases

Default phrases:

```text
ULTRON
Hey ULTRON
```

If the user says only the wake phrase, ULTRON enters `listening`. If the user says a wake phrase plus a command, ULTRON strips the wake phrase and sends only the command through STT and the safe runtime.

## Providers

Wake providers:

| Provider | Notes |
|---|---|
| `text` | Working local fallback that detects wake phrases in transcript payloads. |
| `openwakeword` | Health-checked adapter for future openWakeWord model use. |
| `double_clap` | Adaptive energy-spike gate that detects two claps and opens listening mode only. |
| `mock` | Deterministic tests. |

VAD providers:

| Provider | Notes |
|---|---|
| `energy` | Working fallback that ignores empty/noisy or low-energy input. |
| `silero` | Health-checked adapter for future Silero VAD use. |
| `webrtc` | Health-checked adapter for future WebRTC VAD use. |
| `mock` | Deterministic tests. |

## Configuration

```json
{
  "wake_word_provider": "text",
  "wake_phrases": ["ULTRON", "Hey ULTRON"],
  "wake_model_path": null,
  "vad_provider": "energy",
  "vad_energy_threshold": 0.015,
  "clap_spike_ratio": 7.0,
  "clap_min_rms": 0.012,
  "clap_min_gap_s": 0.05,
  "clap_max_gap_s": 0.35,
  "clap_cooldown_s": 0.45
}
```

The `double_clap` provider adapts the reviewed Jarvis script's useful local logic: adaptive noise floor, spike thresholding, clap gap bounds, retrigger arming, and cooldown. It deliberately excludes ElevenLabs and one-off app launch sequencing. A detected double clap only changes ULTRON into `listening`; the next command still goes through STT, planning, validation, policy, executor, and audit logging.

Environment overrides:

```powershell
$env:ULTRON_WAKE_WORD_PROVIDER = "text"
$env:ULTRON_WAKE_PHRASES = "ULTRON;Hey ULTRON"
$env:ULTRON_WAKE_MODEL_PATH = ".ultron/models/openwakeword"
$env:ULTRON_VAD_PROVIDER = "energy"
$env:ULTRON_VAD_ENERGY_THRESHOLD = "0.015"
```

## API

```text
POST /api/wake/start
POST /api/wake/stop
GET  /api/wake/status
POST /api/wake/process
```

`POST /api/wake/process` accepts candidate speech segments from the browser interface. It returns `ignored` when no wake word is present or the segment is noisy. It only calls STT and the brain when the wake/VAD gates pass.

Push-to-talk still uses:

```text
POST /api/voice/transcribe
```

## Safety

Wake word and VAD are input gates only. They cannot:

- choose tools,
- execute tasks,
- skip schema validation,
- bypass policy,
- bypass confirmation,
- bypass audit logging.

After a wake-authorized command enters the pipeline, it behaves exactly like typed or push-to-talk voice input.
