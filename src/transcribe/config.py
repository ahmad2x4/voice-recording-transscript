from dataclasses import dataclass, field
from pathlib import Path
import os
import shutil


@dataclass
class Config:
    api_key: str = ""
    model: str = "gpt-4o-mini-transcribe"
    output_dir: Path = field(default_factory=Path.cwd)
    device: int | None = None
    use_mic: bool = True
    use_system_audio: bool = True
    teams_only: bool = False
    verbose: bool = False
    teams_pid: int | None = None
    teams_audio_device: int | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            errors.append(
                "OpenAI API key required. Set OPENAI_API_KEY env var or use --api-key."
            )

        if self.model not in ("gpt-4o-mini-transcribe", "gpt-4o-transcribe"):
            errors.append(
                f"Unknown model '{self.model}'. "
                "Use 'gpt-4o-mini-transcribe' or 'gpt-4o-transcribe'."
            )

        if not self.output_dir.is_dir():
            errors.append(f"Output directory does not exist: {self.output_dir}")

        return errors
