"""语音转文本：本地 faster-whisper（默认）或在线 OpenAI API。"""

import io
import os
import threading
import time
from dataclasses import dataclass

CONFIDENCE_THRESHOLD = 0.55

_engine = "local"
_recognizer = None
_model_name = "base"
_lock = threading.Lock()


@dataclass
class STTResult:
    text: str
    confidence: float          # 0~1，<0.55 视为不可执行
    language: str              # "zh"/"en"
    duration_ms: int


def init_stt(engine: str = "local", model: str = "base") -> None:
    """初始化识别引擎；engine ∈ auto|local|api，auto 按 OPENAI_API_KEY 自动判定。"""
    global _engine, _model_name, _recognizer
    eng = (engine or "auto").lower()
    if eng == "auto":
        eng = "api" if os.environ.get("OPENAI_API_KEY") else "local"
    if eng == "api" and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY 未设置，无法使用 api 引擎")
    _engine = eng
    _model_name = model
    with _lock:
        _recognizer = None


def transcribe(wav_bytes: bytes) -> STTResult:
    """wav 字节 → 文本结果（唯一调用点）。"""
    if _engine == "api":
        return _transcribe_api(wav_bytes)
    return _transcribe_local(wav_bytes)


def _transcribe_local(wav_bytes: bytes) -> STTResult:
    global _recognizer
    if _recognizer is None:
        with _lock:
            if _recognizer is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as e:
                    raise RuntimeError("faster-whisper 未安装：pip install faster-whisper（首次会下载模型 ~150MB）") from e
                _recognizer = WhisperModel(_model_name, device="auto", compute_type="int8")
    start = time.monotonic()
    segments, info = _recognizer.transcribe(
        io.BytesIO(wav_bytes), language="zh", vad_filter=True
    )
    segs = list(segments)
    text = "".join(s.text for s in segs).strip()
    if segs:
        avg = sum(s.avg_logprob for s in segs if s.avg_logprob is not None) / len(segs)
        confidence = max(0.0, min(1.0, avg + 1.0))
    else:
        confidence = 0.0
    duration_ms = int((time.monotonic() - start) * 1000)
    language = getattr(info, "language", None) or "zh"
    return STTResult(text=text, confidence=confidence, language=language, duration_ms=duration_ms)


def _transcribe_api(wav_bytes: bytes) -> STTResult:
    """OpenAI /v1/audio/transcriptions（multipart 上传，标准库实现）。"""
    import json
    import urllib.request
    import uuid

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 未设置")
    boundary = "----vc" + uuid.uuid4().hex
    body = bytearray()
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'.encode()
    )
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nzh\r\n'.encode()
    )
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        f'Content-Type: audio/wav\r\n\r\n'.encode()
    )
    body.extend(wav_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    start = time.monotonic()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = (data.get("text") or "").strip()
    return STTResult(
        text=text,
        confidence=0.9,
        language="zh",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _audio_deps():
    """可选音频依赖（numpy/sounddevice/soundfile），未装时给出安装提示。"""
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
        return np, sd, sf
    except ImportError as e:
        raise RuntimeError("录音依赖未安装：pip install sounddevice soundfile") from e


def record_until_release(
    device_idx: int = 0,
    max_sec: int = 15,
    stop_event: threading.Event | None = None,
) -> bytes:
    """录音直到 stop_event 被设置或超时，返回 wav 字节；无声音返回 b""。"""
    np, sd, sf = _audio_deps()
    import queue

    sr = int(sd.query_devices(device_idx, "input")["default_samplerate"])
    q: queue.Queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy())

    frames_total = []
    with sd.InputStream(
        samplerate=sr, device=device_idx, channels=1, callback=callback, dtype="float32"
    ):
        deadline = time.monotonic() + max_sec
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                frames_total.append(q.get(timeout=0.1))
            except queue.Empty:
                continue
    if not frames_total:
        return b""
    audio = np.concatenate(frames_total, axis=0)
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    return buf.getvalue()
