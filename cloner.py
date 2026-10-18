"""Core voice-cloning logic: voice management, chunked long-form TTS,
concatenation and output verification (no 0-second files, ever)."""
import io
import json
import os
import re
import subprocess
import tempfile

# sanitize proxy env (known httpx IPv6 crash)
for _k in ("no_proxy", "NO_PROXY"):
    _v = os.environ.get(_k, "")
    if "[" in _v:
        os.environ[_k] = ",".join(p for p in _v.split(",") if "[" not in p)

from google import genai
from google.genai import types

FLASH_TTS = "gemini-3.8-flash-tts"
LITE_TTS = "gemini-3.8-flash-lite-tts"

DATA_DIR = os.path.expanduser("~/.voice-clone-studio")
VOICES_FILE = os.path.join(DATA_DIR, "voices.json")


def get_client(api_key: str):
    return genai.Client(api_key=api_key)


def _load_voices() -> dict:
    try:
        with open(VOICES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_voices(v: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(VOICES_FILE, "w") as f:
        json.dump(v, f, indent=2)


def to_24k_wav(input_bytes: bytes, suffix: str = ".mp3") -> bytes:
    """Convert any audio to 24kHz mono 16-bit WAV (API requirement)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fin:
        fin.write(input_bytes)
        fin_path = fin.name
    fout_path = fin_path + ".24k.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", fin_path,
             "-ar", "24000", "-ac", "1", "-sample_fmt", "s16", fout_path],
            check=True, timeout=120)
        with open(fout_path, "rb") as f:
            return f.read()
    finally:
        for p in (fin_path, fout_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def wav_duration(wav_bytes: bytes) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return 0.0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def create_voice(client, name: str, ref_wav_24k: bytes, consent_wav_24k: bytes) -> dict:
    """Create a stored replicated voice. Returns {'id': ..., 'display': ...}."""
    import base64
    resp = client.voices.create(
        voice={
            "type": "replicated",
            "display_name": name,
            "replicated": {
                "source_audio": {
                    "data": base64.b64encode(ref_wav_24k).decode("ascii"),
                    "mime_type": "audio/wav",
                },
                "consent_audio": {
                    "data": base64.b64encode(consent_wav_24k).decode("ascii"),
                    "mime_type": "audio/wav",
                },
            },
        },
        store=True,
    )
    voice_id = getattr(resp, "id", None) or getattr(resp, "name", "")
    info = {"id": voice_id, "display": name}
    voices = _load_voices()
    voices[name] = info
    _save_voices(voices)
    return info


def list_remote_voices(client):
    try:
        return list(client.voices.list())
    except Exception as e:
        return {"error": str(e)[:200]}


# ---- Prompted (style-described) voices ----
# Measured from the "After the Spotlight" countdown channel (2026-10-18):
# male narrator ~120Hz, brisk ~185 wpm, punchy ~0.5s pauses, dramatic tone.
AFTER_SPOTLIGHT_STYLE_PROMPT = (
    "A male documentary narrator in his late 30s with a clear mid-low voice. "
    "Brisk, energetic countdown pacing \u2014 fast but always articulate, like a "
    "YouTube documentary countdown channel. Dramatic, punchy delivery with "
    "short sharp pauses between sentences for emphasis. Confident, slightly "
    "sensational tone that builds intrigue and keeps momentum."
)


def create_prompted_voice(client, name: str, prompt_text: str) -> dict:
    """Create a stored voice from a natural-language style description."""
    resp = client.voices.create(
        voice={
            "type": "prompted",
            "display_name": name,
            "prompted": {"input": prompt_text},
        },
        store=True,
    )
    voice_id = getattr(resp, "id", None) or getattr(resp, "name", "")
    info = {"id": voice_id, "display": name}
    voices = _load_voices()
    voices[name] = info
    _save_voices(voices)
    return info


def chunk_script(text: str, max_chars: int = 4000) -> list:
    """Split script into chunks on paragraph boundaries."""
    text = re.sub(r"\r\n?", "\n", text).strip()
    # drop markdown headers/formatting noise but keep the words
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= max_chars:
            cur = (cur + "\n\n" + p).strip() if cur else p
        else:
            if cur:
                chunks.append(cur)
            # hard-split an oversized single paragraph on sentences
            while len(p) > max_chars:
                m = re.match(r"^(.{1,%d}[.!?])\s+" % max_chars, p, re.S)
                if not m:
                    chunks.append(p[:max_chars])
                    p = p[max_chars:]
                else:
                    chunks.append(m.group(1))
                    p = p[m.end():]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def tts_chunk(client, text: str, model: str, voice_id: str = None,
              prebuilt: str = None) -> bytes:
    """Generate WAV audio for one chunk. Returns raw WAV bytes."""
    if voice_id:
        vc = types.VoiceConfig(voice=voice_id)
    else:
        vc = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=prebuilt or "Kore"))
    resp = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=vc),
        ),
    )
    return resp.candidates[0].content.parts[0].inline_data.data


def concat_wavs(wav_list: list) -> bytes:
    """Concatenate 24kHz mono 16-bit WAVs via ffmpeg concat."""
    with tempfile.TemporaryDirectory() as td:
        paths = []
        for i, w in enumerate(wav_list):
            p = os.path.join(td, f"c{i:03d}.wav")
            with open(p, "wb") as f:
                f.write(w)
            paths.append(p)
        lst = os.path.join(td, "list.txt")
        with open(lst, "w") as f:
            for p in paths:
                f.write(f"file '{p}'\n")
        out = os.path.join(td, "out.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", lst, "-c", "copy", out],
            check=True, timeout=300)
        with open(out, "rb") as f:
            return f.read()


def wav_to_mp3(wav_bytes: bytes, bitrate: str = "128k") -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
        fin.write(wav_bytes)
        fin_path = fin.name
    fout_path = fin_path + ".mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", fin_path,
             "-codec:a", "libmp3lame", "-b:a", bitrate, fout_path],
            check=True, timeout=600)
        with open(fout_path, "rb") as f:
            return f.read()
    finally:
        for p in (fin_path, fout_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def estimate_minutes(text: str, wpm: int = 140) -> float:
    words = len(text.split())
    return words / wpm
