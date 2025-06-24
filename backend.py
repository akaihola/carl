"""Pipecat WebRTC Voice Assistant Backend"""

# pyright: reportUnusedFunction=false
# pyright: reportExplicitAny=false
# pyright: reportUnusedParameter=false
# pyright: reportAny=false
# pyright: reportUnusedCallResult=false

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, cast

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport
from pipecat.transports.network.webrtc_connection import (
    IceServer,
    SmallWebRTCConnection,
)

load_dotenv(override=True)

app = FastAPI()

pcs_map: dict[str, SmallWebRTCConnection] = {}

ice_servers = [
    IceServer(
        urls="stun:stun.l.google.com:19302",
    )
]

SYSTEM_MESSAGE = (
    "You are a helpful AI assistant. "
    "Keep your responses brief and conversational. "
    "Your output will be converted to audio "
    "so don't include special characters in your answers."
    ""
)


@app.post("/api/offer")
async def offer(request: dict[str, Any], background_tasks: BackgroundTasks):
    pc_id = request.get("pc_id")
    sdp: str = cast(str, request["sdp"])
    type_: str = cast(str, request["type"])

    if pc_id and pc_id in pcs_map:
        pipecat_connection = pcs_map[pc_id]
        logger.info(f"Reusing existing connection for pc_id: {pc_id}")
        await pipecat_connection.renegotiate(sdp=sdp, type=type_)
    else:
        pipecat_connection = SmallWebRTCConnection(ice_servers)
        await pipecat_connection.initialize(sdp=sdp, type=type_)

        @pipecat_connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            logger.info(
                f"Discarding peer connection for pc_id: {webrtc_connection.pc_id}"
            )
            pcs_map.pop(webrtc_connection.pc_id, None)

        background_tasks.add_task(run_bot, pipecat_connection)

    answer = pipecat_connection.get_answer()
    if answer is not None:
        pcs_map[answer["pc_id"]] = pipecat_connection

    return answer


async def run_bot(webrtc_connection: SmallWebRTCConnection):
    pipecat_transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            audio_out_10ms_chunks=2,
        ),
    )

    assemblyai_api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not assemblyai_api_key:
        raise ValueError("ASSEMBLYAI_API_KEY environment variable is required")
    stt = AssemblyAISTTService(api_key=assemblyai_api_key)

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required")
    llm = OpenAILLMService(
        api_key=openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        model="anthropic/claude-3.5-sonnet",
    )

    context = OpenAILLMContext(
        [
            {
                "role": "system",
                "content": SYSTEM_MESSAGE,
            },
            {
                "role": "user",
                "content": (
                    "Start by greeting the user warmly and introducing yourself."
                ),
            },
        ],
    )
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            pipecat_transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            pipecat_transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @pipecat_transport.event_handler("on_client_connected")
    async def on_client_connected(transport: SmallWebRTCTransport, client: Any):
        logger.info("Pipecat Client connected")
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @pipecat_transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport: SmallWebRTCTransport, client: Any):
        logger.info("Pipecat Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


@app.get("/")
async def serve_index():
    return FileResponse("index.html")


@app.get("/style.css")
async def serve_css():
    return FileResponse("style.css")


@app.get("/webrtc-script.js")
async def serve_js():
    return FileResponse("webrtc-script.js")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    coros = [pc.disconnect() for pc in pcs_map.values()]
    await asyncio.gather(*coros)
    pcs_map.clear()


app.router.lifespan_context = lifespan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC Voice Assistant")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP server (default: 8000)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    logger.remove(0)
    if args.verbose:
        logger.add(sys.stderr, level="TRACE")
    else:
        logger.add(sys.stderr, level="DEBUG")

    uvicorn.run(app, host=args.host, port=args.port)
