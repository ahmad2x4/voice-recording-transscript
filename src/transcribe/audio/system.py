import asyncio
import json
import logging
from collections.abc import AsyncIterator

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000
CHUNK_DURATION_MS = 100
BYTES_PER_SAMPLE = 2  # 16-bit
CHUNK_BYTES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000) * BYTES_PER_SAMPLE


async def _probe_valid_pids(pids: list[int]) -> list[int]:
    """
    Ask AudioTee which PIDs it can actually tap by running it briefly and
    parsing its stderr JSON logs. Returns only the PIDs that translated
    successfully to audio objects.
    """
    cmd = ["audiotee", "--sample-rate", str(SAMPLE_RATE),
           "--include-processes"] + [str(p) for p in pids]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    # Give it a moment to attempt setup, then kill it (it may already have exited)
    await asyncio.sleep(0.5)
    try:
        proc.terminate()
    except ProcessLookupError:
        pass  # Already exited (e.g. due to invalid PIDs)
    _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=3.0)

    valid: list[int] = []
    for line in stderr_bytes.splitlines():
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        msg = entry.get("data", {}).get("message", "")
        ctx = entry.get("data", {}).get("context", {})
        if msg == "Translated PID to process object" and "pid" in ctx:
            valid.append(int(ctx["pid"]))

    log.info("Valid audio PIDs: %s (of %s)", valid, pids)
    return valid


async def system_audio_stream(meeting_pids: list[int] | None = None) -> AsyncIterator[bytes]:
    base_cmd = ["audiotee", "--sample-rate", str(SAMPLE_RATE), "--flush"]

    # Determine which PIDs to use
    pids_to_use: list[int] | None = None
    if meeting_pids:
        valid = await _probe_valid_pids(meeting_pids)
        if valid:
            pids_to_use = valid
        else:
            log.warning("No valid audio PIDs found — falling back to all system audio")
            print("Warning: Could not tap specific app audio. Capturing all system audio.")

    cmd = base_cmd[:]
    if pids_to_use:
        cmd.extend(["--include-processes"] + [str(p) for p in pids_to_use])

    log.info("Starting AudioTee: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    assert proc.stdout is not None

    try:
        while True:
            chunk = await proc.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    except asyncio.CancelledError:
        log.debug("System audio stream cancelled")
        proc.terminate()
        await proc.wait()
        raise
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()

        if proc.returncode and proc.returncode != -15:  # -15 = SIGTERM
            stderr = ""
            if proc.stderr:
                stderr = (await proc.stderr.read()).decode(errors="replace")
            log.error("AudioTee exited with code %d: %s", proc.returncode, stderr)
