import asyncio
import logging
from collections.abc import AsyncIterator

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000
CHUNK_DURATION_MS = 100
BYTES_PER_SAMPLE = 2  # 16-bit
CHUNK_BYTES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000) * BYTES_PER_SAMPLE


async def system_audio_stream(teams_pid: int | None = None) -> AsyncIterator[bytes]:
    cmd = ["audiotee", "--sample-rate", str(SAMPLE_RATE)]
    if teams_pid is not None:
        cmd.extend(["--include-processes", str(teams_pid)])

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
