# Plan C: Local Audio Capture + Gladia API

## Why Plan C?

- **Local capture** — no bot joining your meeting, fully private
- **Gladia** — built-in real-time speaker diarization, 103ms latency, $0.55/hr, 10 hrs/month free
- **Multi-speaker** — Gladia diarizes the system audio stream into Speaker 1, Speaker 2, etc. (Plan A can't do this)

## Architecture

```
┌──────────┐     PCM 16kHz      ┌──────────────────┐
│   Mic    │ ──────────────────▶│ WebSocket #1     │──▶ "You: ..."
│(sounddev)│                    │ Gladia Live API   │
└──────────┘                    └──────────────────┘
                                        │
┌──────────┐     PCM 16kHz      ┌──────────────────┐     ┌─────────┐
│ AudioTee │ ──────────────────▶│ WebSocket #2     │──▶  │ Output  │
│(sys audio)│                   │ Gladia Live API   │     │ Manager │
└──────────┘                    │ (diarization ON)  │     └────┬────┘
                                └──────────────────┘          │
                                                     ┌───────┴───────┐
                                                     │ Terminal      │
                                                     │ + File        │
                                                     └───────────────┘
```

### Why two connections, not one mixed stream?

- **Mic → WS #1** (diarization OFF): Always labeled "You" — guaranteed, no confusion
- **System audio → WS #2** (diarization ON): Gladia separates remote speakers into Speaker 1, Speaker 2, etc.
- Mixing both into one stream would confuse diarization (your mic audio bleeds into system audio labels)

### Audio format

- Gladia expects: PCM 16-bit, 16kHz sample rate (not 24kHz like OpenAI)
- AudioTee: `audiotee --sample-rate 16000`
- sounddevice: `samplerate=16000, channels=1, dtype='int16'`

## File Structure

```
src/transcribe/
  __init__.py
  cli.py              # Click CLI entry point
  config.py            # Config dataclass + validation
  audio/
    __init__.py
    mic.py             # sounddevice → async generator of PCM chunks
    system.py          # AudioTee subprocess → async generator of PCM chunks
  gladia/
    __init__.py
    client.py          # Gladia WebSocket client (connect, send audio, receive transcripts)
    protocol.py        # Session init message builder, audio frame builder
  teams.py             # Detect active Teams meeting (pgrep MSTeams)
  output.py            # Colored terminal display + file writer
  session.py           # Orchestrator: wires everything together
```

## CLI Interface

```
transcribe [OPTIONS]

  --output-dir PATH  Where to save transcripts (default: current dir)
  --device INT       Mic device index
  --list-devices     List mic devices and exit
  --no-mic           System audio only
  --no-system-audio  Mic only (no AudioTee needed)
  --teams-only       Only capture Teams process audio via AudioTee
  --verbose          Debug logging
```

Note: No `--model` flag needed — Gladia uses their own Solaria-1 model. API key via `GLADIA_API_KEY` env var.

## Gladia WebSocket Protocol

### Connection flow:

1. **HTTP POST** to `https://api.gladia.io/v2/live` to get a session URL
   ```json
   {
     "encoding": "wav/pcm",
     "sample_rate": 16000,
     "bit_depth": 16,
     "channels": 1,
     "language_config": {
       "languages": ["en"]
     },
     "realtime_processing": {
       "words_accurate_timestamps": true
     }
   }
   ```
   For the system audio connection, add:
   ```json
   {
     "realtime_processing": {
       "speaker_diarization": true
     }
   }
   ```

2. **WebSocket connect** to the returned session URL

3. **Send audio** as raw binary frames (no base64, no JSON wrapping — just raw PCM bytes)

4. **Receive events**:
   - `transcript` with `type: "partial"` — interim results (update current line)
   - `transcript` with `type: "final"` — completed utterance (commit to file)
   - Each final transcript includes `speaker` field (integer) when diarization is ON

5. **End session**: Send `{"type": "stop"}` JSON message

### Key differences from OpenAI Realtime API:
- Audio sent as raw binary, not base64 JSON
- Simpler protocol — no `session.update`, no `input_audio_buffer.append`
- Diarization is a first-class feature, not a workaround
- 16kHz sample rate (vs 24kHz for OpenAI)

## Component Details

### `gladia/client.py` — WebSocket Client

Class `GladiaLiveClient`:
- `__init__(self, api_key, label, output_queue, enable_diarization=False)`
- `create_session()` — POST to Gladia API, returns WebSocket URL
- `connect()` — opens WebSocket to session URL
- `send_audio(chunk: bytes)` — sends raw PCM bytes directly
- `receive_loop()` — parses incoming transcript events:
  - Partial: `TranscriptDelta(label, text, timestamp)`
  - Final: `TranscriptComplete(label, text, timestamp, speaker=N)`
  - For mic connection: speaker is always "You"
  - For system audio: speaker is "Speaker 1", "Speaker 2", etc. from Gladia
- `stop()` — sends stop message, closes WebSocket
- `run(audio_source: AsyncIterator[bytes])` — main loop: connect, send audio, receive transcripts

### `gladia/protocol.py` — Message Builders

- `build_session_config(enable_diarization: bool) -> dict` — POST body for session creation
- `build_stop_message() -> str` — `{"type": "stop"}`

### `audio/mic.py` — Microphone Capture

- `sounddevice.InputStream` with `samplerate=16000, channels=1, dtype='int16'`
- Async generator yielding 100ms chunks (1600 samples = 3200 bytes)
- Callback thread → asyncio.Queue bridge via `loop.call_soon_threadsafe`

### `audio/system.py` — System Audio via AudioTee

- `asyncio.create_subprocess_exec("audiotee", "--sample-rate", "16000")`
- Optionally: `"--include-processes", str(teams_pid)` for Teams-only
- Read stdout in 3200-byte chunks (100ms at 16kHz 16-bit mono)
- Handle process lifecycle and errors

### `teams.py` — Teams Detection

```python
async def detect_teams_meeting() -> Optional[int]:
    # 1. pgrep -x MSTeams
    # 2. Return PID if found, None otherwise
```

### `output.py` — Output Manager

- Receives events from both WebSocket clients via shared asyncio.Queue
- **Terminal**: ANSI colored output
  - `[14:30:05] You: Hello everyone...` (green)
  - `[14:30:08] Speaker 1: Hi, thanks for joining...` (blue)
  - `[14:30:12] Speaker 2: Good morning...` (yellow)
  - Partial results update current line with `\r`
  - Final results commit line and move to next
- **File**: `transcript_2026-03-15_14-30.txt`
  - Only final/completed utterances
  - Format: `[HH:MM:SS] Speaker: text`

### `session.py` — Orchestrator

```python
async def run(config: Config):
    output_queue = asyncio.Queue()
    output_mgr = OutputManager(output_queue, config.output_dir)

    async with asyncio.TaskGroup() as tg:
        # Always start output consumer
        tg.create_task(output_mgr.run())

        # Mic stream (if enabled)
        if config.use_mic:
            mic_client = GladiaLiveClient(
                api_key=config.api_key,
                label="You",
                output_queue=output_queue,
                enable_diarization=False,
            )
            mic_source = MicCapture(device=config.device)
            tg.create_task(mic_client.run(mic_source))

        # System audio stream (if enabled)
        if config.use_system_audio:
            sys_client = GladiaLiveClient(
                api_key=config.api_key,
                label="Remote",
                output_queue=output_queue,
                enable_diarization=True,
            )
            sys_source = SystemAudioCapture(teams_pid=config.teams_pid)
            tg.create_task(sys_client.run(sys_source))

        # Wait for Ctrl+C
        await shutdown_event.wait()

    output_mgr.flush()
    print(f"Transcript saved to {output_mgr.file_path}")
```

## Implementation Phases

### Phase 1 — Mic-only transcription
1. Create `pyproject.toml` and package structure
2. Implement `config.py` with validation
3. Implement `gladia/protocol.py`
4. Implement `gladia/client.py` with single WebSocket
5. Implement `audio/mic.py`
6. Implement basic `output.py` (terminal only)
7. Implement minimal `cli.py` — mic-only mode
8. Test: speak into mic, see live transcription

### Phase 2 — System audio + dual streams
9. Implement `audio/system.py` (AudioTee subprocess)
10. Implement `teams.py`
11. Implement `session.py` orchestrator with both streams
12. Update `cli.py` with all flags
13. Test: play audio on Mac, see it transcribed with speaker labels

### Phase 3 — Polish
14. Add file output to `output.py`
15. Add colored terminal output with speaker labels
16. Error handling (API key missing, AudioTee not installed, no mic)
17. `--list-devices` support
18. Graceful shutdown with summary
19. README with install instructions

## Dependencies

```toml
[project]
name = "transcribe"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0",
    "websockets>=12.0",
    "sounddevice>=0.4",
    "numpy>=1.24",
    "httpx>=0.27",
]

[project.scripts]
transcribe = "transcribe.cli:main"
```

- `httpx` for the initial POST to create Gladia session (async HTTP)
- System: `audiotee` via `brew install makeusabrew/tap/audiotee`

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| AudioTee requires process to be playing audio | Default to all system audio; `--teams-only` for PID filtering |
| Two Gladia sessions doubles cost | Still only $1.10/hr total; offer `--no-mic` / `--no-system-audio` |
| Gladia free tier limit (10 hrs/month) | Warn user when approaching limit; support `--no-system-audio` for mic-only |
| AudioTee not installed | Pre-flight check with `shutil.which`, print install command |
| WebSocket disconnect | Reconnect with backoff; buffer audio during reconnection |
| New Teams version changes process name | Make process name configurable or check multiple candidates |

## Plan A vs Plan C Comparison

| Aspect | Plan A (OpenAI) | Plan C (Gladia) |
|--------|----------------|-----------------|
| Diarization | "You" vs "Remote" only | Full multi-speaker |
| Cost | ~$3.60/hr (mini) | ~$1.10/hr |
| Free tier | No | 10 hrs/month |
| Latency | ~200ms | ~103ms |
| Protocol complexity | Higher (JSON-wrapped audio) | Lower (raw binary audio) |
| Python SDK | Raw WebSocket | GladiaPy available |
| Audio format | PCM 24kHz | PCM 16kHz |
