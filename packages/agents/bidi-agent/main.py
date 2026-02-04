import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from strands.experimental.bidi.models import BidiNovaSonicModel
from strands.experimental.bidi.types.events import (
    BidiTextInputEvent,
    BidiAudioInputEvent,
    BidiAudioStreamEvent,
    BidiTranscriptStreamEvent,
    BidiConnectionStartEvent,
    BidiResponseStartEvent,
    BidiResponseCompleteEvent,
    BidiInterruptionEvent,
)

logger = logging.getLogger(__name__)

TIMEZONE_TO_LANGUAGE: dict[str, str] = {
    "Asia/Seoul": "Korean",
    "Asia/Tokyo": "Japanese",
    "Asia/Shanghai": "Chinese",
    "Asia/Kolkata": "Hindi",
    "Asia/Calcutta": "Hindi",
    "Europe/Paris": "French",
    "Europe/Berlin": "German",
    "Europe/Rome": "Italian",
    "Europe/Madrid": "Spanish",
    "America/Sao_Paulo": "Portuguese",
    "America/Mexico_City": "Spanish",
}

BASE_SYSTEM_PROMPT = """You are a warm, professional, and helpful female AI assistant. \
Give accurate answers that sound natural, direct, and human. \
Start by answering the user's question clearly in 1-2 sentences. \
Then, expand only enough to make the answer understandable, staying within 3-5 short sentences total. \
Avoid sounding like a lecture or essay."""

LANGUAGE_MIRROR_PROMPT = """
CRITICAL LANGUAGE MIRRORING RULES:
- Always reply in the language spoken. DO NOT mix with English. However, if the user talks in English, reply in English.
- Please respond in the language the user is talking to you in, If you have a question or suggestion, ask it in the language the user is talking in. I want to ensure that our communication remains in the same language as the user."""


def build_system_prompt(timezone: str) -> str:
    language = TIMEZONE_TO_LANGUAGE.get(timezone)
    if language:
        return (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            f"The user's timezone is {timezone}. "
            f"Default to {language} unless the user speaks a different language.\n"
            f"{LANGUAGE_MIRROR_PROMPT}"
        )
    return f"{BASE_SYSTEM_PROMPT}\n{LANGUAGE_MIRROR_PROMPT}"


app = FastAPI()


@app.get("/ping")
async def ping():
    return {"status": "healthy"}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        # First message: config (voice, system_prompt)
        config_msg = await websocket.receive_json()
    except (WebSocketDisconnect, json.JSONDecodeError):
        return

    model = BidiNovaSonicModel(
        model_id="amazon.nova-2-sonic-v1:0",
        provider_config={
            "audio": {
                "voice": config_msg.get("voice", "tiffany"),
            },
        },
        client_config={"region": "us-east-1"},
    )

    try:
        timezone = config_msg.get("browser_time_zone", "")
        custom_prompt = config_msg.get("system_prompt")
        system_prompt = custom_prompt or build_system_prompt(timezone)
        await model.start(system_prompt=system_prompt)
    except Exception:
        logger.exception("Failed to start BidiNovaSonicModel")
        await websocket.close(code=1011, reason="Failed to start model")
        return

    async def browser_to_bedrock():
        """Forward messages from browser WebSocket to BidiNovaSonicModel."""
        try:
            async for msg in websocket.iter_json():
                msg_type = msg.get("type")
                if msg_type == "text":
                    await model.send(BidiTextInputEvent(text=msg["text"]))
                elif msg_type == "audio":
                    await model.send(
                        BidiAudioInputEvent(
                            audio=msg["audio"],
                            format="pcm",
                            sample_rate=16000,
                            channels=1,
                        )
                    )
                elif msg_type == "stop":
                    break
        except WebSocketDisconnect:
            pass

    async def bedrock_to_browser():
        """Forward events from BidiNovaSonicModel to browser WebSocket."""
        try:
            async for event in model.receive():
                if isinstance(event, BidiAudioStreamEvent):
                    await websocket.send_json(
                        {
                            "type": "audio",
                            "audio": event.audio,
                            "sample_rate": event.sample_rate,
                        }
                    )
                elif isinstance(event, BidiTranscriptStreamEvent):
                    await websocket.send_json(
                        {
                            "type": "transcript",
                            "text": event.text,
                            "role": event.role,
                            "is_final": event.is_final,
                        }
                    )
                elif isinstance(event, BidiConnectionStartEvent):
                    await websocket.send_json(
                        {
                            "type": "connection_start",
                            "connection_id": event.connection_id,
                        }
                    )
                elif isinstance(event, BidiResponseStartEvent):
                    await websocket.send_json({"type": "response_start"})
                elif isinstance(event, BidiResponseCompleteEvent):
                    await websocket.send_json({"type": "response_complete"})
                elif isinstance(event, BidiInterruptionEvent):
                    await websocket.send_json(
                        {
                            "type": "interruption",
                            "reason": event.reason,
                        }
                    )
        except WebSocketDisconnect:
            pass

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(browser_to_bedrock())
            tg.create_task(bedrock_to_browser())
    except* WebSocketDisconnect:
        pass
    finally:
        await model.stop()
