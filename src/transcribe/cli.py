import asyncio
import logging
import sys
from pathlib import Path

import click

from .audio.mic import list_devices
from .config import Config
from .prompt import _SKIP, select_meeting, select_mic
from .session import run


@click.command()
@click.option(
    "--model",
    type=click.Choice(["gpt-4o-mini-transcribe", "gpt-4o-transcribe"]),
    default="gpt-4o-mini-transcribe",
    help="OpenAI transcription model.",
)
@click.option(
    "--output-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="transcripts",
    help="Directory to save transcript files (default: ./transcripts).",
)
@click.option(
    "--mic",
    "mic_device",
    type=int,
    default=None,
    help="Mic input device index (skips interactive prompt). Use --list-devices to see options.",
)
@click.option(
    "--meeting",
    "meeting_app",
    type=str,
    default=None,
    help='Meeting app to capture audio from, e.g. "teams", "zoom" (skips interactive prompt).',
)
@click.option(
    "--list-devices", "show_devices", is_flag=True, help="List audio input devices and exit."
)
@click.option("--no-mic", is_flag=True, help="Disable mic capture.")
@click.option("--no-meeting", is_flag=True, help="Disable meeting/system audio capture.")
@click.option("--api-key", default=None, help="OpenAI API key (or set OPENAI_API_KEY).")
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def main(
    model: str,
    output_dir: Path,
    mic_device: int | None,
    meeting_app: str | None,
    show_devices: bool,
    no_mic: bool,
    no_meeting: bool,
    api_key: str | None,
    verbose: bool,
) -> None:
    """Real-time meeting transcription from mic and system audio."""
    if show_devices:
        click.echo(list_devices())
        return

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if no_mic and no_meeting:
        click.echo("Error: Cannot disable both mic and meeting audio.", err=True)
        sys.exit(1)

    # Interactive mic selection
    chosen_mic: int | None = None
    if not no_mic:
        chosen_mic = select_mic(preselected=mic_device)

    # Interactive meeting selection
    chosen_meeting_pid: int | None = None
    chosen_meeting_name: str = ""
    use_system_audio = not no_meeting

    if use_system_audio:
        result = asyncio.run(select_meeting(preselected=meeting_app))
        if isinstance(result, type(_SKIP)):
            use_system_audio = False
        elif result is None:
            # "all system audio" — no PID filter
            chosen_meeting_name = "all system audio"
        else:
            chosen_meeting_pid = result.pid
            chosen_meeting_name = result.name

    config = Config(
        api_key=api_key or "",
        model=model,
        output_dir=output_dir,
        mic_device=chosen_mic,
        meeting_pid=chosen_meeting_pid,
        meeting_name=chosen_meeting_name,
        use_mic=not no_mic,
        use_system_audio=use_system_audio,
        verbose=verbose,
    )

    errors = config.validate()
    if errors:
        for e in errors:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    asyncio.run(run(config))
