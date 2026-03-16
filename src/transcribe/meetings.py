"""Detect running meeting applications on macOS."""
import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Known meeting apps: (display name, exact process names, partial/bundle fallbacks)
KNOWN_APPS: list[tuple[str, list[str], list[str]]] = [
    # (display name, exact process names, partial/bundle fallbacks)
    # For multi-process apps, exact names lists ALL process names used by the app.
    # AudioTee will tap audio from all of them, ensuring no audio is missed.
    ("Microsoft Teams", [
        "MSTeams",
        "Microsoft Teams WebView",
        "Microsoft Teams WebView Helper",
        "Microsoft Teams WebView Helper (GPU)",
        "Microsoft Teams WebView Helper (Renderer)",
        "Microsoft Teams WebView Helper (Plugin)",
    ], ["com.microsoft.teams2"]),
    ("Zoom",     ["zoom.us", "Zoom", "ZoomWebviewHelper"], ["zoom.us"]),
    ("Webex",    ["Webex", "Webex Meetings"],              ["com.cisco.webex"]),
    ("Slack",    ["Slack", "Slack Helper", "Slack Helper (Renderer)"], ["com.tinyspeck.slackmacgap"]),
    ("Discord",  ["Discord", "Discord Helper", "Discord Helper (Renderer)"], ["com.hnc.Discord"]),
    ("Google Meet", [], ["Google Chrome Helper"]),
]


@dataclass
class MeetingApp:
    name: str
    pids: list[int] = field(default_factory=list)

    @property
    def primary_pid(self) -> int:
        return self.pids[0]


async def _pgrep_all(args: list[str]) -> list[int]:
    """Return all matching PIDs."""
    proc = await asyncio.create_subprocess_exec(
        "pgrep", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode == 0 and stdout.strip():
        return [int(p) for p in stdout.strip().split(b"\n") if p.strip()]
    return []


async def detect_meeting_apps() -> list[MeetingApp]:
    """Return all currently running meeting apps with all their PIDs."""
    found: list[MeetingApp] = []
    seen: set[str] = set()

    for display_name, exact_names, partial_names in KNOWN_APPS:
        if display_name in seen:
            continue

        all_pids: list[int] = []

        # Collect PIDs from ALL known process names for this app (runs in parallel)
        if exact_names:
            results = await asyncio.gather(*[_pgrep_all(["-x", name]) for name in exact_names])
            for pids in results:
                all_pids.extend(pids)

        # If no exact match at all, try partial fallback to confirm app is running
        if not all_pids:
            for name in partial_names:
                pids = await _pgrep_all(["-f", name])
                if pids:
                    all_pids.extend(pids)
                    break

        if all_pids:
            found.append(MeetingApp(name=display_name, pids=all_pids))
            seen.add(display_name)
            log.info("Detected '%s' with %d process(es): %s", display_name, len(all_pids), all_pids)

    return found
