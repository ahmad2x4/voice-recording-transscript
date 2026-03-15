# transcribe

Real-time meeting transcription from your microphone and system audio (e.g. Microsoft Teams, Zoom), streamed live to your terminal and saved to a file.

Uses the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime-transcription) and [AudioTee](https://github.com/makeusabrew/audiotee) for system audio capture.

> **macOS only** — requires macOS 14.2+ (Sonoma) for system audio capture via Core Audio Taps.

---

## Requirements

- macOS 14.2+
- Python 3.11+
- An [OpenAI API key](https://platform.openai.com/api-keys)

---

## Installation

### 1. Clone the repo

```bash
git clone <repo-url>
cd voice-recording-transscript
```

### 2. Install AudioTee (for system audio capture)

AudioTee captures system audio using Apple's Core Audio Taps API. Build it from source:

```bash
git clone https://github.com/makeusabrew/audiotee /tmp/audiotee
cd /tmp/audiotee
swift build -c release
cp .build/release/audiotee /usr/local/bin/audiotee
```

> **Note:** On first run, macOS will ask your terminal for **Screen & System Audio Recording** permission. Grant it in System Settings → Privacy & Security → Screen & System Audio Recording.

### 3. Install the Python package

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 4. Set your OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

Add this to your `~/.zshrc` or `~/.bashrc` to make it permanent.

---

## Usage

```bash
source .venv/bin/activate

# Full meeting: your mic + system audio (Teams, Zoom, etc.)
transcribe

# Your microphone only
transcribe --no-system-audio

# System audio only (what others say)
transcribe --no-mic

# Use the higher accuracy model
transcribe --model gpt-4o-transcribe

# Save transcript to a specific folder
transcribe --output-dir ~/transcripts

# List available microphone devices
transcribe --list-devices

# Use a specific microphone
transcribe --device 0
```

Press `Ctrl+C` to stop. A transcript file is saved automatically as `transcript_YYYY-MM-DD_HH-MM.txt` in the current directory (or `--output-dir`).

---

## Example output

```
[14:30:05] You: Hey everyone, can you hear me okay?
[14:30:09] Remote: Yeah, loud and clear. Let's get started.
[14:30:13] You: Great. So today I want to walk through the Q1 results.
```

---

## Models

| Model | Speed | Accuracy | Cost |
|-------|-------|----------|------|
| `gpt-4o-mini-transcribe` (default) | Faster | Good | Lower |
| `gpt-4o-transcribe` | Slower | Better | Higher |

---

## How it works

1. **Mic** — captured via `sounddevice` and streamed to OpenAI as "You"
2. **System audio** — captured via AudioTee (Core Audio Taps) and streamed to OpenAI as "Remote"
3. Two parallel WebSocket connections to the OpenAI Realtime API handle VAD and transcription
4. Results are printed live and written to a timestamped `.txt` file
