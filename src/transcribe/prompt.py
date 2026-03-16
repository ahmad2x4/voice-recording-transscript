"""Interactive prompts for mic and meeting selection."""
import asyncio

import sounddevice as sd

from .meetings import MeetingApp, detect_meeting_apps


def _pick(options: list[str], prompt: str, allow_skip: bool = True) -> int | None:
    """
    Print a numbered list and return the chosen index (0-based into options),
    or None if the user skips. Returns None immediately if options is empty.
    """
    for i, label in enumerate(options, 1):
        print(f"  [{i}] {label}")
    if allow_skip:
        print("  [0] Skip")

    while True:
        raw = input(f"{prompt}: ").strip()
        if raw == "0" and allow_skip:
            return None
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        valid = f"1-{len(options)}" + (", 0 to skip" if allow_skip else "")
        print(f"  Please enter {valid}.")


def select_mic(preselected: int | None) -> int | None:
    """Return a sounddevice device index for the mic, or None for system default."""
    if preselected is not None:
        return preselected

    devices = sd.query_devices()
    input_devices = [
        (i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0
    ]
    default_idx = sd.default.device[0]

    if not input_devices:
        print("No input devices found. Using system default.")
        return None

    print("\nSelect microphone:")
    labels = []
    for dev_idx, dev in input_devices:
        suffix = " (system default)" if dev_idx == default_idx else ""
        labels.append(f"{dev['name']}{suffix}")

    chosen = _pick(labels, "Enter number (default: system default)", allow_skip=True)
    if chosen is None:
        return None
    return input_devices[chosen][0]


async def select_meeting(preselected: str | None) -> MeetingApp | None:
    """
    Return a MeetingApp to capture audio from, or None for all system audio.
    preselected can be an app name fragment (e.g. "teams", "zoom").
    """
    apps = await detect_meeting_apps()

    # If a name was given on the CLI, try to match it
    if preselected is not None:
        needle = preselected.lower()
        for app in apps:
            if needle in app.name.lower():
                print(f"Meeting app matched: {app.name} (PID {app.pid})")
                return app
        if apps:
            print(f"No running app matching '{preselected}'. Choose from detected apps:")
        else:
            print(f"No running meeting apps found matching '{preselected}'.")
            print("Falling back to all system audio.")
            return None

    print("\nSelect meeting app for system audio:")
    if not apps:
        print("  No known meeting apps detected.")
        labels = ["All system audio", "Skip (mic only)"]
        chosen = _pick(labels, "Enter number", allow_skip=False)
        return None if chosen == 0 else _SKIP

    labels = [f"{app.name} (PID {app.pid})" for app in apps]
    labels.append("All system audio")

    chosen = _pick(labels, "Enter number (0 to skip meeting audio)", allow_skip=True)
    if chosen is None:
        return _SKIP         # user chose 0 = no meeting audio
    if chosen == len(apps):
        return None          # "All system audio"
    return apps[chosen]


# Sentinel — means "user explicitly chose no meeting audio"
class _SkipSentinel:
    pass

_SKIP = _SkipSentinel()
