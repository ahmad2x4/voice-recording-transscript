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
from .teams import detect_teams_process

log = logging.getLogger(__name__)


async def run(config: Config) -> None:
    if config.use_system_audio:
        if shutil.which("audiotee"):
            config.teams_pid = await detect_teams_process()
            if config.teams_pid:
                print(f"Teams process detected (PID {config.teams_pid}). Capturing Teams audio via AudioTee.")
            elif config.teams_only:
                print("No Teams process detected. Exiting.")
                return
            else:
                print("Capturing all system audio via AudioTee.")
        elif config.teams_only:
            print("AudioTee not installed. Cannot capture system audio.")
            print("Build from source: git clone https://github.com/makeusabrew/audiotee && cd audiotee && swift build -c release")
            return
        else:
            print("AudioTee not installed. Falling back to mic-only mode.")
            print("To capture system audio, build AudioTee from source:")
            print("  git clone https://github.com/makeusabrew/audiotee && cd audiotee && swift build -c release\n")
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
        sources.append("mic")
    if config.use_system_audio:
        sources.append("system audio (AudioTee)")
    print(f"Transcribing from: {', '.join(sources)}")
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
                mic_audio = mic_stream(device=config.device)
                tg.create_task(mic_client.run(mic_audio))

            if config.use_system_audio:
                sys_client = RealtimeTranscriptionClient(
                    api_key=config.api_key,
                    model=config.model,
                    label="Remote",
                    output_queue=output_queue,
                )
                sys_audio = system_audio_stream(teams_pid=config.teams_pid)
                tg.create_task(sys_client.run(sys_audio))

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
