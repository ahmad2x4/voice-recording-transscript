import asyncio
import logging
import sys
from pathlib import Path

import click

from .audio.mic import list_devices
from .config import Config
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
@click.option("--device", type=int, default=None, help="Mic input device index.")
@click.option(
    "--list-devices", "show_devices", is_flag=True, help="List audio devices and exit."
)
@click.option("--no-mic", is_flag=True, help="Disable mic capture (system audio only).")
@click.option(
    "--no-system-audio",
    is_flag=True,
    help="Disable system audio capture (mic only).",
)
@click.option(
    "--teams-only",
    is_flag=True,
    help="Only capture Teams audio. Exit if no Teams meeting found.",
)
@click.option("--api-key", default=None, help="OpenAI API key (or set OPENAI_API_KEY).")
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def main(
    model: str,
    output_dir: Path,
    device: int | None,
    show_devices: bool,
    no_mic: bool,
    no_system_audio: bool,
    teams_only: bool,
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

    if no_mic and no_system_audio:
        click.echo("Error: Cannot disable both mic and system audio.", err=True)
        sys.exit(1)

    if teams_only:
        no_mic = True
        no_system_audio = False

    config = Config(
        api_key=api_key or "",
        model=model,
        output_dir=output_dir,
        device=device,
        use_mic=not no_mic,
        use_system_audio=not no_system_audio,
        teams_only=teams_only,
        verbose=verbose,
    )

    errors = config.validate()
    if errors:
        for e in errors:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    asyncio.run(run(config))
