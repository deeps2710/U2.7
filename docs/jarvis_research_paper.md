# Research Paper / Technical Survey: Local-First Jarvis-Style Voice Assistant

**Project goal:** Build a personal voice-controlled AI assistant for a consumer laptop that can open apps, control volume/brightness, search files, run approved scripts, manage notes/reminders, and later extend to smart-home control, scheduling, and proactive assistance.

**Generated:** 2026-06-13

---

## Abstract

A Jarvis-like personal assistant should not be built as an unrestricted chatbot with shell access. The safer and more reliable architecture is a local-first, tool-based voice agent: wake-word detection and voice activity detection run continuously on-device, speech is transcribed by local or cloud STT, an LLM maps the utterance to a small allowlisted tool schema, a policy layer validates and gates the action, the local executor performs the OS operation, and a TTS component responds. For laptop control, deterministic tools and safety gates matter more than open-ended autonomy. Public datasets for exact “voice command → laptop action” pairs are limited, so a practical dataset plan combines a small hand-labeled command set, synthetic paraphrases, public spoken-language-understanding corpora, and real usage logs with human correction.

---

## 1. Recommended Architecture

### 1.1 Pipeline

```text
wake word -> VAD/endpointing -> STT -> command normalization -> LLM planner
-> JSON tool call -> schema validator -> risk/permission policy -> OS executor
-> observation/result -> response summarizer -> TTS
```

The best current practical architecture is a cascaded streaming pipeline, not a fully autonomous end-to-end speech-to-action model. A 2026 realtime voice-agent paper demonstrates a practical STT -> LLM/function-calling -> TTS architecture using Deepgram, vLLM, and ElevenLabs, reporting P50 time-to-first-audio around 947 ms under tested conditions [voice-agent-2026]. This is relevant because a laptop assistant needs debuggability and controllable execution.

### 1.2 Local vs cloud choices

| Component | Local choice | Cloud choice | Recommendation |
|---|---|---|---|
| Wake word | openWakeWord, Howl, Porcupine | Usually unnecessary | Local only |
| VAD | Silero VAD, WebRTC VAD | Built into realtime APIs | Local Silero VAD |
| STT | faster-whisper, whisper.cpp, Vosk | OpenAI, Deepgram, AssemblyAI | Local by default; cloud fallback |
| LLM | Ollama/llama.cpp with Qwen/Llama/Mistral | GPT/Claude/Gemini | Hybrid routing |
| Tool execution | Python + OS APIs | Remote automation services | Local, allowlisted, sandboxed |
| TTS | Piper, Coqui forks, Kokoro | ElevenLabs, OpenAI, Azure | Piper first; premium cloud voice later |

---

## 2. Speech Components

### 2.1 Wake word

Use **openWakeWord** for open-source, local wake-word detection. It supports pretrained models and custom wake words [openwakeword]. Howl is also a useful academic reference because it was deployed as an open-source wake-word system in Firefox Voice [howl].

Recommended implementation:
- Wake phrase: “Hey Jarvis” or custom phrase.
- Run wake detector continuously.
- After wake event, start VAD + STT stream.
- Add cooldown and false-positive suppression.
- Log false wakeups for future tuning.

### 2.2 Voice Activity Detection

Use **Silero VAD**. It is fast enough for realtime use on a normal CPU; its documentation reports 30+ ms chunks processed in under 1 ms on one CPU thread [silero-vad].

Why it matters:
- Detects speech start/end.
- Reduces STT cost and latency.
- Enables barge-in and interruption later.
- Avoids sending silence to the STT model.

### 2.3 Speech-to-text

| Engine | Strength | Weakness | Use case |
|---|---|---|---|
| faster-whisper / whisper.cpp | Accurate, multilingual, robust | Chunking needed for streaming; larger models need more resources | Best general local STT |
| Vosk | Lightweight, offline, streaming, constrained vocab possible | Lower open-ended accuracy than Whisper | Low-latency command grammar |
| Cloud STT | Best latency/accuracy in noisy realtime | Cost/privacy/network dependency | Optional fallback |

Whisper is a strong baseline because it was trained on 680k hours of multilingual/multitask audio [whisper]. Vosk is useful for an always-on command system because it has small offline streaming models; Vosk documentation describes small models around 50 MB and ~300 MB runtime RAM [vosk].

Recommended:
- Start with faster-whisper small/base.
- Use Vosk only for very constrained command grammar or extremely low-resource mode.
- Log STT transcript and corrected transcript to improve dataset.

### 2.4 Text-to-speech

| Engine | Strength | Weakness | Use case |
|---|---|---|---|
| Piper | Fast, local, lightweight | Less natural than premium voices | Default offline feedback |
| Coqui/XTTS forks | Better quality, voice-cloning style options | Heavier, maintenance fragmentation | Experimental local premium voice |
| ElevenLabs/OpenAI TTS | Natural, expressive, streaming | Cost/privacy/network | Premium voice mode |

Piper is a strong local default. Its voice catalog includes quality levels from small x_low voices around 5–7M parameters to high voices around 28–32M parameters [piper-samples].

---

## 3. LLM Backbone

### 3.1 Local LLM

Use **Ollama** for easy model management or **llama.cpp** for maximum control. llama.cpp supports function/tool calling formats for several local model families including Llama, Qwen, Hermes, Mistral Nemo, and others [llamacpp-tools].

Recommended local models:
- Qwen instruct/coder family for structured JSON/tool use.
- Llama instruct family for general command reasoning.
- Mistral/Nemo-style models for lightweight use.

Local LLM pros:
- Private.
- Offline.
- No API cost.
- Good for simple commands.

Local LLM cons:
- More tool-call errors.
- CPU latency can be high.
- Weaker ambiguity handling.
- Needs strict output validation.

### 3.2 API LLM

OpenAI-style function calling uses a five-step flow: send available tools, receive a tool call, execute in the app, send tool output back, and receive a final answer [openai-tools]. This pattern is ideal for controlled execution because the model requests tools but your program remains responsible for actual execution.

API LLM pros:
- Stronger reasoning.
- Better function calling.
- Better multi-step planning.
- Better clarification generation.

API LLM cons:
- Cost.
- Internet dependency.
- Privacy tradeoff.

### 3.3 Routing policy

Use local tools/rules first:

```text
if command is deterministic and low-risk:
    use local parser or local LLM
elif command is ambiguous/multi-step:
    use cloud LLM planner
elif command is high-risk:
    generate preview and ask confirmation
```

Examples:
- “Open Spotify” -> deterministic local tool.
- “Set volume to 40%” -> deterministic local tool.
- “Find my latest resume and email Rahul” -> cloud planner + confirmation.
- “Delete old videos from Downloads” -> preview only, require confirmation.

---

## 4. OS-Level Control and Safety

### 4.1 OS control libraries

| Task | Windows | macOS | Linux |
|---|---|---|---|
| App launch | PowerShell, Start Menu shortcuts, subprocess | `open`, AppleScript | `xdg-open`, `.desktop`, subprocess |
| Volume | pycaw, PowerShell | AppleScript/CoreAudio tools | pactl/amixer |
| Brightness | WMI/PowerShell | AppleScript or system tools | brightnessctl |
| GUI automation | pywinauto, PyAutoGUI | PyAutoGUI, AppleScript | PyAutoGUI, xdotool/wmctrl |
| Files | pathlib, shutil | pathlib, shutil | pathlib, shutil |
| App-specific automation | COM/pywin32 | ScriptingBridge/PyObjC | DBus/CLI APIs |

### 4.2 Safety model

Do **not** give the LLM unrestricted shell access. Open Interpreter’s safety docs explicitly warn that running LLM-generated code on your computer is inherently risky [openinterpreter-safety]. AutoGPT similarly restricts file access to a workspace and warns against disabling this unless inside Docker/VM [autogpt-workspace].

Recommended execution model:

```text
LLM proposes tool call
-> JSON schema validation
-> path normalization
-> allowlist check
-> risk policy
-> optional confirmation
-> executor
-> audit log
```

Risk levels:
- LOW: open app, set volume, search files, read calendar.
- MEDIUM: move/rename files, create notes, draft email.
- HIGH: delete files, send email, run script, install software, edit startup items.
- BLOCKED: arbitrary shell, credential access, disabling security tools, exfiltrating files.

---

## 5. Tool Schema Design

Good tools should be small, typed, and deterministic.

Bad:
```json
{"name": "control_computer", "description": "Do anything on the computer"}
```

Good:
```json
{
  "name": "set_system_volume",
  "description": "Set laptop speaker volume to a percentage.",
  "parameters": {
    "type": "object",
    "properties": {
      "level": {"type": "integer", "minimum": 0, "maximum": 100}
    },
    "required": ["level"]
  }
}
```

Recommended first tool set:
1. open_application
2. close_application
3. set_system_volume
4. change_system_volume
5. mute_audio
6. set_brightness
7. search_files
8. open_file
9. open_folder
10. create_note
11. append_to_note
12. set_timer
13. set_reminder
14. get_calendar_events
15. create_calendar_event_draft
16. draft_email
17. take_screenshot
18. read_clipboard
19. copy_to_clipboard
20. run_approved_script

Tool-call output should be machine-readable:
```json
{
  "status": "success",
  "message": "Volume set to 40%",
  "changed": {"volume": 40}
}
```

---

## 6. Existing Projects and Lessons

### Leon AI
Useful for modular assistant design, privacy-aware self-hosting, skills/tools, and extensibility. Lesson: large assistant frameworks can be harder to adapt than a small purpose-built tool layer.

### Mycroft / OpenVoiceOS
Useful for voice assistant skills and smart-home integrations. Lesson: traditional skill systems are stable but can feel rigid compared with LLM tool routing.

### Open Interpreter
Useful for local computer control. Lesson: powerful code execution must be sandboxed and permissioned.

### AutoGPT
Useful for agent loops and autonomous task planning. Lesson: broad autonomy is overkill for low-latency laptop control; use workspace restrictions and approval gates.

### Common pitfalls
- Letting the LLM run arbitrary shell.
- Relying on GUI automation for everything.
- No structured tool schema.
- No risk levels.
- No audit log.
- No dataset of failures.
- No command preview before destructive actions.
- Too much cloud dependency for always-on voice.

---

## 7. Dataset Strategy

There is no perfect large public dataset for:
```text
spoken laptop command -> OS-specific safe tool call -> verified execution result
```

Use a staged dataset:

### Stage A: Hand-labeled seed set
- 50–200 examples.
- Cover each tool.
- Include ambiguous commands and refusal cases.
- Include OS variants.

### Stage B: Synthetic paraphrases
For each seed:
- casual phrasing
- short command
- polite version
- typo/STT-like transcript
- Hindi-English or local language variants if needed
- ambiguous variant

### Stage C: Real usage logs
Log:
- audio metadata
- STT transcript
- corrected transcript
- model tool call
- validated tool call
- execution result
- user correction
- risk decision

### Stage D: Evaluation split
Recommended split:
- train 70%
- validation 15%
- test 15%
- keep real-world failures as a separate regression test set

### Public datasets to reuse

| Dataset | What it gives | Limitation |
|---|---|---|
| SLURP | spoken assistant-style intents/slots | not laptop-control specific |
| MASSIVE | large multilingual virtual-assistant NLU | text only; not OS execution |
| Speech-MASSIVE | speech version of MASSIVE subset | still general assistant domains |
| Fluent Speech Commands | real spoken smart-home commands | narrow action/object/location schema |
| Google Speech Commands | keyword spotting | one-word commands, not full tasks |
| Snips NLU | intent/slot benchmark style | older, limited domains |

MASSIVE has 1M utterances across 51 languages, 18 domains, 60 intents, and 55 slots [massive]. Fluent Speech Commands has 30,043 utterances from 97 speakers, each with action/object/location labels [fluent-speech]. Speech-MASSIVE extends part of MASSIVE into speech for 12 languages [speech-massive].

---

## 8. Evaluation Metrics

Measure each layer separately:
1. Wake-word false accept rate and false reject rate.
2. VAD endpointing latency.
3. STT word error rate.
4. Intent accuracy.
5. Slot accuracy.
6. Tool-call JSON validity.
7. Execution success rate.
8. Unsafe-action block rate.
9. Clarification quality.
10. End-to-end latency.

Minimum acceptable prototype target:
- Low-risk intent accuracy: >95%
- Tool JSON validity: >99%
- High-risk confirmation accuracy: 100% for destructive actions
- Median command-to-action latency: under 2 seconds locally for simple commands

---

## 9. Recommended MVP Build Plan

### Week 1
- Text-only CLI.
- Tool schema.
- JSON validation.
- Basic tools: open app, volume, brightness, search files.
- Audit log.

### Week 2
- Add STT with faster-whisper.
- Add Piper TTS.
- Add confirmation system.
- Add 100–300 example dataset.

### Week 3
- Add wake word + VAD.
- Add local/cloud LLM router.
- Add real usage logging.
- Add regression tests for dangerous actions.

### Week 4+
- Calendar/email draft integrations.
- Smart-home APIs.
- Memory/preferences.
- Proactive reminders.
- GUI automation only where API control is unavailable.

---

## 10. Final Recommendation

Build a safe local automation system where the LLM is a planner, not the owner of the computer. Use local speech components, local deterministic tools, and an optional API LLM fallback. Your dataset should focus less on generic chatbot responses and more on exact structured tool calls, slot extraction, confirmation behavior, and execution outcomes.
