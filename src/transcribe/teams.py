import asyncio
import logging

import sounddevice as sd

log = logging.getLogger(__name__)

TEAMS_PROCESS_NAMES = ["MSTeams", "Microsoft Teams"]
TEAMS_AUDIO_DEVICE_NAME = "Microsoft Teams Audio"


async def detect_teams_process() -> int | None:
    for name in TEAMS_PROCESS_NAMES:
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-x", name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout.strip():
            pid = int(stdout.strip().split(b"\n")[0])
            log.info("Detected Teams process '%s' with PID %d", name, pid)
            return pid

    log.info("No Teams process detected")
    return None


def find_teams_audio_device() -> int | None:
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if TEAMS_AUDIO_DEVICE_NAME in dev["name"] and dev["max_input_channels"] > 0:
            log.info(
                "Found Teams audio device: '%s' (index %d)", dev["name"], i
            )
            return i
    log.info("No Teams audio device found")
    return None
