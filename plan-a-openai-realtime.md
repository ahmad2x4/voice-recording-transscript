# Plan A: OpenAI Realtime API + AudioTee

## Architecture

```
┌──────────┐     PCM 24kHz      ┌──────────────────┐
│   Mic    │ ──────────────────▶│ WebSocket #1     │──▶ "You: ..."
│(sounddev)│                    │ OpenAI Realtime   │
└──────────┘                    └──────────────────┘
                                        │
┌──────────┐     PCM 24kHz      ┌──────────────────┐     ┌─────────┐
│ AudioTee │ ──────────────────▶│ WebSocket #2     │──▶  │ Output  │
│(sys audio)│                   │ OpenAI Realtime   │     │ Manager │
└──────────┘                    └──────────────────┘     └────┬────┘
                                                              │
                                                     ┌───────┴───────┐
                                                     │ Terminal      │
                                                     │ + File        │
                                                     └───────────────┘
```

Two separate WebSocket connections — mic labeled "You", system audio labeled "Remote". Clean speaker separation without multiplexing.

## File Structure

```
src/transcribe/
  __init__.py
  cli.py              # Click CLI (--model, --device, --list-devices, --no-mic, --no-system-audio, etc.)
  config.py            # Config dataclass + validation
  audio/
    __init__.py
    mic.py             # sounddevice → async generator of PCM chunks
    system.py          # AudioTee subprocess → async generator of PCM chunks
  realtime/
    __init__.py
    client.py          # WebSocket client (connect, send audio, receive transcripts)
    protocol.py        # JSON message builders (session.update, input_audio_buffer.append)
  teams.py             # Detect active Teams meeting (pgrep MSTeams)
  output.py            # Colored terminal display + file writer
  session.py           # Orchestrator: wires everything together
```

## CLI Interface

```
transcribe [OPTIONS]

  --model TEXT        gpt-4o-mini-transcribe | gpt-4o-transcribe (default: mini)
  --output-dir PATH  Where to save transcripts (default: current dir)
  --device INT       Mic device index
  --list-devices     List mic devices and exit
  --no-mic           System audio only
  --no-system-audio  Mic only
  --teams-only       Only capture Teams process audio
  --verbose          Debug logging
```

## Implementation Phases

### Phase 1 — Single mic stream working end-to-end
1. Create `pyproject.toml` and package structure
2. Implement `config.py` with validation
3. Implement `realtime/protocol.py` (pure functions)
4. Implement `realtime/client.py` with a single WebSocket connection
5. Implement `audio/mic.py`
6. Implement basic `output.py` (print to terminal only)
7. Implement minimal `cli.py` that captures mic and transcribes
8. Test end-to-end with mic only

### Phase 2 — System audio + dual streams
9. Implement `audio/system.py` (AudioTee subprocess)
10. Implement `teams.py` (Teams detection)
11. Implement `session.py` orchestrator with dual streams
12. Update `cli.py` with all flags
13. Test with both streams

### Phase 3 — Polish
14. Add file output to `output.py`
15. Add colored terminal output with speaker labels
16. Add error handling (API key missing, AudioTee not installed, WebSocket disconnect, etc.)
17. Add `--list-devices` support
18. Add graceful shutdown with summary

## Key Design Decisions

- **Diarization V1**: "You" vs "Remote" via separate streams. Multi-speaker remote diarization is V2 using batch `gpt-4o-transcribe-diarize`
- **Teams detection**: `pgrep -x MSTeams` → if found, optionally pass PID to AudioTee's `--include-processes`
- **asyncio** throughout, using `asyncio.TaskGroup` (Python 3.11+)
- **100ms audio chunks** (4800 bytes at 24kHz 16-bit mono) for low latency

## Dependencies

- Python: `click`, `websockets`, `sounddevice`, `numpy`
- System: `audiotee` (via `brew install makeusabrew/tap/audiotee`)

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| AudioTee requires process to be playing audio at start | Default to all system audio; only use PID filtering with `--teams-only` |
| Two WebSocket connections doubles API cost | Offer `--no-system-audio` / `--no-mic` flags; default to cheaper mini model |
| AudioTee not installed | Check at startup with `shutil.which`, print install instructions |
| WebSocket disconnects | Reconnection with exponential backoff; buffer audio during reconnect |
| Thread/async boundary for sounddevice | Use `asyncio.Queue` with `loop.call_soon_threadsafe` from callback thread |
