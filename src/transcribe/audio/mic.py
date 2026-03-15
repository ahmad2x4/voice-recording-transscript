import asyncio
import logging
from collections.abc import AsyncIterator

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
CHUNK_DURATION_MS = 100
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)


def list_devices() -> str:
    return str(sd.query_devices())


async def mic_stream(device: int | None = None) -> AsyncIterator[bytes]:
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        if status:
            log.warning("sounddevice status: %s", status)
        loop.call_soon_threadsafe(queue.put_nowait, indata.tobytes())

    log.info(
        "Opening mic (device=%s, rate=%d, chunk=%dms)",
        device,
        SAMPLE_RATE,
        CHUNK_DURATION_MS,
    )

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=CHUNK_SAMPLES,
        device=device,
        callback=callback,
    ):
        log.info("Mic stream started")
        try:
            while True:
                chunk = await queue.get()
                yield chunk
        except asyncio.CancelledError:
            log.debug("Mic stream cancelled")
            raise
