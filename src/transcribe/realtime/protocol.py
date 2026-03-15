import base64
import json

WS_URL = "wss://api.openai.com/v1/realtime"


def ws_url(model: str) -> str:
    return f"{WS_URL}?intent=transcription"


def ws_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }


def build_session_update(model: str) -> str:
    return json.dumps(
        {
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": model,
                    "language": "en",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "input_audio_noise_reduction": {
                    "type": "near_field",
                },
            },
        }
    )


def build_audio_append(pcm_bytes: bytes) -> str:
    audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")
    return json.dumps(
        {
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }
    )
