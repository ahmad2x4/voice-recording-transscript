import asyncio
import logging
import shutil
import signal
from datetime import datetime

from .audio.mic import mic_stream
from .audio.system import system_audio_stream
from .config import Config
from .output import OutputManager
from .realtime.client import RealtimeTranscriptionClient, TranscriptEvent

log = logging.getLogger(__name__)


async def run(config: Config) -> None:
    if config.use_system_audio:
        if not shutil.which("audiotee"):
            print("AudioTee not installed. Falling back to mic-only mode.")
            print("To capture system audio, build AudioTee from source:")
            print("  git clone https://github.com/makeusabrew/audiotee")
            print("  cd audiotee && swift build -c release")
            print("  cp .build/release/audiotee /usr/local/bin/audiotee\n")
            config.use_system_audio = False

    output_queue: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
    output_mgr = OutputManager(output_queue, config.output_dir)

    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    start_time = datetime.now()

    sources: list[str] = []
    if config.use_mic:
        sources.append(f"mic (device {config.mic_device})" if config.mic_device is not None else "mic")
    if config.use_system_audio:
        label = config.meeting_name or "all system audio"
        sources.append(f"system audio ({label})")
    print(f"\nTranscribing from: {', '.join(sources)}")
    print(f"Model: {config.model}")
    print("Press Ctrl+C to stop.\n")

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(output_mgr.run())

            if config.use_mic:
                mic_client = RealtimeTranscriptionClient(
                    api_key=config.api_key,
                    model=config.model,
                    label="You",
                    output_queue=output_queue,
                )
                tg.create_task(mic_client.run(mic_stream(device=config.mic_device)))

            if config.use_system_audio:
                sys_client = RealtimeTranscriptionClient(
                    api_key=config.api_key,
                    model=config.model,
                    label="Remote",
                    output_queue=output_queue,
                )
                tg.create_task(sys_client.run(system_audio_stream(meeting_pids=config.meeting_pids or None)))

            await shutdown.wait()
            raise KeyboardInterrupt

    except* KeyboardInterrupt:
        pass

    duration = datetime.now() - start_time
    minutes = int(duration.total_seconds() // 60)
    seconds = int(duration.total_seconds() % 60)

    print(f"\nSession ended. Duration: {minutes}m {seconds}s")
    if output_mgr.file_path:
        print(f"Transcript saved to: {output_mgr.file_path}")
