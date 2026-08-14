"""测试 STT：引擎判定、本地识别（mock）、API 上传（mock）、录音（mock）。"""

import importlib.util

import pytest

from voiceconsole import stt


def test_init_auto_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    stt.init_stt("auto")
    assert stt._engine == "api"


def test_init_auto_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stt.init_stt("auto")
    assert stt._engine == "local"


def test_init_api_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        stt.init_stt("api")


def test_init_local_ok(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stt.init_stt("local")
    assert stt._engine == "local"


def test_transcribe_local_mock(monkeypatch):
    class FakeSeg:
        text = "打开桌面"
        avg_logprob = -0.1

    class FakeInfo:
        language = "zh"

    class FakeModel:
        def transcribe(self, *a, **kw):
            return iter([FakeSeg()]), FakeInfo()

    monkeypatch.setattr(stt, "_engine", "local")
    monkeypatch.setattr(stt, "_recognizer", FakeModel())
    res = stt.transcribe(b"fake-wav")
    assert res.text == "打开桌面"
    assert 0.0 <= res.confidence <= 1.0
    assert res.language == "zh"
    assert res.duration_ms >= 0


def test_transcribe_local_missing_package(monkeypatch):
    monkeypatch.setattr(stt, "_engine", "local")
    monkeypatch.setattr(stt, "_recognizer", None)
    if importlib.util.find_spec("faster_whisper") is None:
        with pytest.raises(RuntimeError):
            stt.transcribe(b"x")


def test_transcribe_api_mock(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    stt.init_stt("api")
    import json as json_mod

    class FakeResp:
        def read(self):
            return json_mod.dumps({"text": "打开桌面"}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured = {}

    def fake_urlopen(req, timeout=60):
        captured["headers"] = req.headers
        captured["url"] = req.full_url
        return FakeResp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = stt.transcribe(b"RIFF-wav-bytes")
    assert res.text == "打开桌面"
    assert res.language == "zh"
    assert "Authorization" in captured["headers"]
    assert "api.openai.com" in captured["url"]


def test_transcribe_api_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stt.init_stt("local")  # 保证状态可回退
    monkeypatch.setattr(stt, "_engine", "api")
    with pytest.raises(RuntimeError):
        stt.transcribe(b"x")


def test_record_until_release_mock(monkeypatch):
    import threading
    import time

    class FakeBlock:
        def copy(self):
            return "block"

    class FakeSD:
        @staticmethod
        def query_devices(idx, kind):
            return {"default_samplerate": 16000}

        class InputStream:
            def __init__(self, **kw):
                self.cb = kw["callback"]

            def __enter__(self):
                for _ in range(3):
                    self.cb(FakeBlock(), None, None, None)
                return self

            def __exit__(self, *a):
                return False

    class FakeNp:
        @staticmethod
        def concatenate(frames, axis=0):
            return frames[0]

    class FakeSf:
        @staticmethod
        def write(buf, audio, sr, format="WAV"):
            buf.write(b"RIFF-fake")

    monkeypatch.setattr(stt, "_audio_deps", lambda: (FakeNp, FakeSD, FakeSf))

    stop = threading.Event()

    def stopper():
        time.sleep(0.2)
        stop.set()

    threading.Thread(target=stopper, daemon=True).start()
    data = stt.record_until_release(max_sec=5, stop_event=stop)
    assert data == b"RIFF-fake"
