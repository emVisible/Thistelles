import os
import shutil
import struct
import threading
import wave

import pyaudio

from . import log as log_mod

logger = log_mod.get_logger()

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

TEMP_DIR = os.path.expanduser("~/.voice-input/tmp")


def _clean_temp_dir():
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)
    except Exception:
        pass


class Recorder:
    def __init__(self):
        self._recording = False
        self._frames: list[bytes] = []
        self._thread: threading.Thread | None = None
        self._stream = None
        self._pyaudio_instance = None
        self._latest_amplitude = 0.0
        self._lock = threading.Lock()
        self._error: str | None = None
        _clean_temp_dir()

    @property
    def recording(self):
        return self._recording

    @property
    def latest_amplitude(self) -> float:
        with self._lock:
            return self._latest_amplitude

    def start(self):
        if self._recording:
            return
        logger.debug("recording: opening audio stream")
        self._recording = True
        self._frames = []
        self._latest_amplitude = 0.0
        self._error = None
        self._thread = threading.Thread(target=self._record, daemon=True)
        self._thread.start()

    @staticmethod
    def _compute_rms(data: bytes) -> float:
        count = len(data) // 2
        shorts = struct.unpack(f"<{count}h", data)
        sum_sq = sum(s * s for s in shorts)
        rms = (sum_sq / count) ** 0.5 / 32768.0
        return min(rms * 4.0, 1.0)

    def _record(self):
        try:
            self._pyaudio_instance = pyaudio.PyAudio()
            self._stream = self._pyaudio_instance.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            logger.debug("recording: stream opened")
        except Exception as e:
            self._error = str(e)
            logger.error("recording: pyaudio init failed: %s", e)
            self._recording = False
            return

        try:
            while self._recording:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self._frames.append(data)
                with self._lock:
                    self._latest_amplitude = self._compute_rms(data)
        finally:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            if self._pyaudio_instance:
                try:
                    self._pyaudio_instance.terminate()
                except Exception:
                    pass
                self._pyaudio_instance = None

    def stop(self) -> str | None:
        if not self._recording:
            return None
        self._recording = False
        if self._thread:
            self._thread.join()
            self._thread = None

        if self._error:
            logger.error("recording: error: %s", self._error)
            return None

        if not self._frames:
            logger.warning("recording: no frames captured")
            return None

        os.makedirs(TEMP_DIR, exist_ok=True)
        path = os.path.join(TEMP_DIR, "recording.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(RATE)
            wf.writeframes(b"".join(self._frames))
        dur = len(self._frames) * CHUNK / RATE
        logger.info("recording: saved (%.1fs, %d frames)", dur, len(self._frames))
        return path
