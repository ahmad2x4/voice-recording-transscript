import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

import websockets

from .protocol import build_audio_append, build_session_update, ws_headers, ws_url

log = logging.getLogger(__name__)


@dataclass
class TranscriptEvent:
    label: str  # "You" or "Remote"
    text: str
    timestamp: datetime
    is_final: bool
    item_id: str = ""


class RealtimeTranscriptionClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        label: str,
        output_queue: asyncio.Queue[TranscriptEvent],
    ):
        self.api_key = api_key
        self.model = model
        self.label = label
        self.output_queue = output_queue
        self._ws: websockets.ClientConnection | None = None

    async def run(self, audio_source: AsyncIterator[bytes]) -> None:
        url = ws_url(self.model)
        headers = ws_headers(self.api_key)

        log.info("Connecting to OpenAI Realtime API for '%s'...", self.label)

        async with websockets.connect(
            url, additional_headers=headers, max_size=None
        ) as ws:
            self._ws = ws

            # Wait for session.created, then send our config
            configured = False
            async for msg in ws:
                event = json.loads(msg)
                event_type = event.get("type", "")
                if event_type == "transcription_session.created":
                    log.info("Session created for '%s'. Sending config...", self.label)
                    await ws.send(build_session_update(self.model))
                elif event_type == "transcription_session.updated":
                    log.info("Session configured for '%s'", self.label)
                    configured = True
                    break
                elif event_type == "error":
                    error_msg = event.get("error", {}).get("message", str(event))
                    raise RuntimeError(f"OpenAI error: {error_msg}")
                else:
                    log.debug("[%s] Setup event: %s", self.label, event_type)

            if not configured:
                raise RuntimeError("WebSocket closed before session was configured")

            # Run send and receive concurrently
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._send_loop(audio_source))
                tg.create_task(self._receive_loop())

    async def _send_loop(self, audio_source: AsyncIterator[bytes]) -> None:
        assert self._ws is not None
        try:
            async for chunk in audio_source:
                await self._ws.send(build_audio_append(chunk))
        except asyncio.CancelledError:
            log.debug("Send loop cancelled for '%s'", self.label)
            raise

    async def _receive_loop(self) -> None:
        assert self._ws is not None
        try:
            async for msg in self._ws:
                event = json.loads(msg)
                await self._handle_event(event)
        except websockets.exceptions.ConnectionClosed:
            log.warning("WebSocket closed for '%s'", self.label)
        except asyncio.CancelledError:
            log.debug("Receive loop cancelled for '%s'", self.label)
            raise

    async def _handle_event(self, event: dict) -> None:
        event_type = event.get("type", "")

        if event_type == "conversation.item.input_audio_transcription.delta":
            await self.output_queue.put(
                TranscriptEvent(
                    label=self.label,
                    text=event.get("delta", ""),
                    timestamp=datetime.now(),
                    is_final=False,
                    item_id=event.get("item_id", ""),
                )
            )

        elif event_type == "conversation.item.input_audio_transcription.completed":
            await self.output_queue.put(
                TranscriptEvent(
                    label=self.label,
                    text=event.get("transcript", ""),
                    timestamp=datetime.now(),
                    is_final=True,
                    item_id=event.get("item_id", ""),
                )
            )

        elif event_type == "input_audio_buffer.speech_started":
            log.debug("[%s] Speech started", self.label)

        elif event_type == "input_audio_buffer.speech_stopped":
            log.debug("[%s] Speech stopped", self.label)

        elif event_type == "input_audio_buffer.committed":
            log.debug("[%s] Audio committed: %s", self.label, event.get("item_id"))

        elif event_type == "error":
            error = event.get("error", {})
            log.error(
                "[%s] API error: %s", self.label, error.get("message", str(error))
            )

        elif event_type in (
            "transcription_session.created",
            "transcription_session.updated",
        ):
            pass  # Already handled during setup

        else:
            log.debug("[%s] Unhandled event: %s", self.label, event_type)
