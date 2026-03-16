"""Detect running meeting applications on macOS."""
import asyncio
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Known meeting apps: (display name, bundle ID or executable names to try)
# Uses pgrep -x (exact) first, then pgrep -f (partial) as fallback
KNOWN_APPS: list[tuple[str, list[str], list[str]]] = [
    # (display name, exact process names, partial/bundle fallbacks)
    ("Microsoft Teams", ["MSTeams"],         ["com.microsoft.teams2", "teams2"]),
    ("Zoom",            ["zoom.us", "Zoom"],  ["zoom.us"]),
    ("Webex",           ["Webex"],            ["com.cisco.webex", "CiscoWebex"]),
    ("Slack",           ["Slack"],            ["com.tinyspeck.slackmacgap"]),
    ("Discord",         ["Discord"],          ["com.hnc.Discord"]),
    ("Google Meet",     [],                   ["Google Chrome Helper"]),  # Meet runs in browser
]


@dataclass
class MeetingApp:
    name: str
    pid: int


async def _pgrep(args: list[str]) -> int | None:
    proc = await asyncio.create_subprocess_exec(
        "pgrep", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode == 0 and stdout.strip():
        return int(stdout.strip().split(b"\n")[0])
    return None


async def detect_meeting_apps() -> list[MeetingApp]:
    """Return all currently running meeting apps."""
    found: list[MeetingApp] = []
    seen: set[str] = set()

    for display_name, exact_names, partial_names in KNOWN_APPS:
        if display_name in seen:
            continue

        pid: int | None = None

        # Try exact match first
        for name in exact_names:
            pid = await _pgrep(["-x", name])
            if pid:
                break

        # Fall back to partial/bundle match
        if not pid:
            for name in partial_names:
                pid = await _pgrep(["-f", name])
                if pid:
                    break

        if pid:
            found.append(MeetingApp(name=display_name, pid=pid))
            seen.add(display_name)
            log.info("Detected '%s' (PID %d)", display_name, pid)

    return found
