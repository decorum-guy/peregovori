"""OpenAI-compatible demo API on Intelion. Run with python -m inference.server."""
import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from .config import ROOT, QwenSettings
from .runtime import InferenceError, QwenRuntime

logger = logging.getLogger("qwen_inference")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=24000)


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    messages: List[ChatMessage] = Field(min_length=2, max_length=160)
    max_tokens: int = Field(default=600, ge=1, le=1024)
    temperature: float = Field(default=0.75, ge=0, le=2)
    stream: bool = False
    adapter_fingerprint: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_dialogue(self):
        if self.messages[0].role != "system" or self.messages[-1].role != "user" or any(m.role == "system" for m in self.messages[1:]):
            raise ValueError("Нужна системная инструкция персонажа и последний ход user.")
        return self


def create_app(settings=None, runtime=None):
    settings = settings or QwenSettings.from_env()
    runtime = runtime or QwenRuntime(settings)
    state = {"status": "loading", "error": None}
    busy = asyncio.Lock()

    async def load():
        try:
            await asyncio.to_thread(runtime.load)
            if not runtime.ready:
                raise ValueError("Adapter was not loaded")
            state["status"] = "ready"
            logger.info("Model and LoRA ready base=%s model=%s", settings.base_model, settings.model_name)
        except Exception as exc:
            state.update(status="error", error="Загрузка модели не завершена. Проверьте preflight, зависимости и свободную VRAM.")
            runtime.ready = False
            logger.error("Model load failed type=%s; run python -m inference.preflight --gpu", type(exc).__name__)

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(load())
        yield
        if not task.done():
            task.cancel()

    app = FastAPI(title="Qwen demo inference", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = runtime

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        # Pydantic's default response includes input; never echo the private role prompt.
        return JSONResponse(status_code=422, content={"error": {"message": "Некорректный chat request.", "code": "invalid_request"}})

    @app.get("/health")
    async def health():
        ready = state["status"] == "ready" and runtime.ready
        return {"status": state["status"], "ready": ready, "base_model": settings.base_model,
                "model": settings.model_name, "adapter_loaded": ready,
                "adapter_fingerprint": runtime.fingerprint if ready else "", "error": state["error"]}

    @app.post("/v1/chat/completions")
    async def complete(request: ChatRequest):
        def error(status, message, code):
            return JSONResponse(status_code=status, content={"error": {"message": message, "code": code}})
        if state["status"] != "ready" or not runtime.ready:
            return error(503, "База и LoRA ещё не загружены.", "model_not_ready")
        if request.model != settings.model_name or (request.adapter_fingerprint and request.adapter_fingerprint != runtime.fingerprint):
            return error(409, "Выбранная модель или checkpoint отличаются от загруженных.", "model_changed")
        if request.stream:
            return error(400, "Streaming в демо не поддерживается.", "stream_unsupported")
        if busy.locked():
            return error(429, "Модель отвечает на предыдущий запрос. Повторите позже.", "model_busy")
        async with busy:
            try:
                text, prompt_tokens, generated_tokens = await asyncio.to_thread(
                    runtime.generate, [m.model_dump() for m in request.messages], request.max_tokens, request.temperature)
            except InferenceError as exc:
                return error(exc.status, str(exc), exc.code)
            except Exception as exc:
                logger.warning("Generation failed type=%s", type(exc).__name__)
                return error(502, "Qwen не смогла ответить. Проверьте VRAM и повторите запрос.", "generation_failed")
        return {"id": "chatcmpl-" + uuid.uuid4().hex, "object": "chat.completion", "created": int(time.time()),
                "model": settings.model_name, "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                                         "finish_reason": "length" if generated_tokens >= min(request.max_tokens, settings.max_new_tokens) else "stop"}],
                "usage": {"prompt_tokens": int(prompt_tokens), "completion_tokens": int(generated_tokens),
                          "total_tokens": int(prompt_tokens + generated_tokens)}}
    return app


def main():
    import uvicorn
    logs = ROOT / "inference/logs"
    logs.mkdir(mode=0o700, exist_ok=True)
    log_file = logs / "qwen.log"
    log_file.touch(mode=0o600, exist_ok=True)
    log_file.chmod(0o600)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_file)])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Avoid library progress / trace dumps with request URLs or hub credentials.
    from transformers.utils import logging as hf_logging
    hf_logging.set_verbosity_error()
    hf_logging.disable_progress_bar()
    settings = QwenSettings.from_env()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port, workers=1, access_log=False, log_config=None)


if __name__ == "__main__":
    main()
