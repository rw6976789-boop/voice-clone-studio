"""Voice Cloning Studio — upload YOUR reference voice + consent once,
then generate long-form voiceovers (up to 1 hour) in one click."""
import os
import time

import streamlit as st

import cloner

st.set_page_config(page_title="Voice Cloning Studio", page_icon="🎙️", layout="wide")
st.title("🎙️ Voice Cloning Studio")

# ---------- API key ----------
api_key = None
try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    pass
with st.sidebar:
    st.header("⚙️ Settings")
    if api_key:
        st.success("Gemini API key: ✅ (from Secrets)")
    else:
        api_key = st.text_input("Gemini API key", type="password",
                                help="Paste your Gemini API key (AI Studio).")
    model = st.selectbox(
        "Voice model",
        [cloner.FLASH_TTS, cloner.LITE_TTS],
        format_func=lambda m: "Flash TTS (best quality)" if "flash-tts" in m and "lite" not in m else "Flash-Lite TTS (cheaper/faster)",
        help="Flash = best quality. Lite = cheaper & faster for bulk.")
    bitrate = st.selectbox("MP3 quality", ["128k", "96k", "192k"], index=0,
                           help="128k is plenty for voiceover.")

if not api_key:
    st.warning("⬅️ Pehle sidebar mein apni Gemini API key dalo.")
    st.stop()

client = cloner.get_client(api_key)

tab1, tab2 = st.tabs(["🎤 My Voice (one-time setup)", "🔊 Generate Voiceover"])

# ================= TAB 1: voice setup =================
with tab1:
    st.subheader("Apni voice clone karo — sirf ek baar")
    st.info(
        "Tumhein **2 audio files** chahiye:\n"
        "1. **Reference voice** — tumhari awaz, 30 second ya zyada, saaf recording (koi bhi format: MP3/WAV/M4A).\n"
        "2. **Consent clip** — tum khud bolo: *\"I consent to the cloning of my voice for text-to-speech.\"* (10 second kafi hai).\n\n"
        "⚠️ Note: yahan **koi pehle se set voice nahi hai** — jo voice tum upload karoge, sirf wahi clone hogi.",
        icon="ℹ️")

    col1, col2 = st.columns(2)
    with col1:
        ref_file = st.file_uploader("1️⃣ Reference voice (tumhari awaz)",
                                    type=["mp3", "wav", "m4a", "ogg", "flac"])
        if ref_file:
            st.audio(ref_file)
    with col2:
        consent_file = st.file_uploader("2️⃣ Consent clip (ijazat wali recording)",
                                       type=["mp3", "wav", "m4a", "ogg", "flac"])
        if consent_file:
            st.audio(consent_file)

    voice_name = st.text_input("Is voice ka naam", value="My Voice")

    if st.button("🚀 Create My Cloned Voice", type="primary",
                 disabled=not (ref_file and consent_file and voice_name.strip())):
        with st.spinner("Voice ban rahi hai... (30-60 second)"):
            try:
                t0 = time.time()
                ref_wav = cloner.to_24k_wav(ref_file.read(),
                                            suffix="." + ref_file.name.split(".")[-1])
                consent_wav = cloner.to_24k_wav(consent_file.read(),
                                                suffix="." + consent_file.name.split(".")[-1])
                rd, cd = cloner.wav_duration(ref_wav), cloner.wav_duration(consent_wav)
                if rd < 25:
                    st.error(f"Reference voice sirf {rd:.0f} second hai — kam az kam 30 second ki do.")
                    st.stop()
                info = cloner.create_voice(client, voice_name.strip(), ref_wav, consent_wav)
                st.success(f"✅ Voice tayyar! ID: `{info['id']}` ({time.time()-t0:.0f}s)")
                st.info("Ye ID Google par 1 saal tak save rahegi. Neeche se kabhi bhi use kar sakte ho.",
                        icon="💾")
            except Exception as e:
                msg = str(e)
                if "billing" in msg.lower() or "permission" in msg.lower():
                    st.error("❌ API ne mana kar diya — lagta hai is key par billing/permission chahiye. "
                             "AI Studio mein billing enable karo ya doosri key try karo.")
                elif "consent" in msg.lower():
                    st.error("❌ Consent verify nahi hui — consent clip mein SAHI speaker (tum) saaf bole: "
                             "\"I consent to the cloning of my voice for text-to-speech.\"")
                else:
                    st.error(f"❌ Error: {msg[:400]}")

    st.divider()
    st.divider()
    st.subheader("🎭 Style se voice banao (bina recording ke)")
    st.caption("Apni awaz record kiye baghair — sirf style describe karo, Google wesi voice bana dega.")
    p_name = st.text_input("Style voice ka naam", value="Countdown Narrator")
    p_prompt = st.text_area(
        "Voice style describe karo",
        value=cloner.AFTER_SPOTLIGHT_STYLE_PROMPT,
        height=120,
        help="Pehle se bhara hua: After the Spotlight jesa countdown-narrator style (tez ~185 wpm, dramatic). Apne lafzon mein badal bhi sakte ho.")
    if st.button("✨ Style Voice Banao", disabled=not (p_name.strip() and p_prompt.strip())):
        with st.spinner("Style voice ban rahi hai..."):
            try:
                info = cloner.create_prompted_voice(client, p_name.strip(), p_prompt.strip())
                st.success(f"✅ Style voice tayyar! ID: `{info['id']}`")
            except Exception as e:
                st.error(f"❌ Error: {str(e)[:400]}")

    st.divider()
    st.subheader("Meri saved voices")
    voices = cloner._load_voices()
    if voices:
        for n, v in voices.items():
            st.write(f"🎙️ **{n}** — `{v['id']}`")
    else:
        st.caption("Abhi koi voice nahi — upar se banao.")

# ================= TAB 2: generate =================
with tab2:
    st.subheader("Script se voiceover banao (1 click, 1 ghante tak)")
    voices = cloner._load_voices()
    if not voices:
        st.warning("Pehle 'My Voice' tab mein apni voice banao.")
        st.stop()

    voice_choice = st.selectbox("Kaunsi voice?", list(voices.keys()))
    voice_id = voices[voice_choice]["id"]

    col1, col2 = st.columns(2)
    with col1:
        script_file = st.file_uploader("Script file (.md / .txt)", type=["md", "txt", "text"])
    with col2:
        pasted = st.text_area("Ya script yahan paste karo", height=150)

    script_text = ""
    if script_file:
        script_text = script_file.read().decode("utf-8", errors="ignore")
    elif pasted.strip():
        script_text = pasted

    if script_text.strip():
        chunks = cloner.chunk_script(script_text)
        est = cloner.estimate_minutes(script_text)
        st.info(f"📄 {len(script_text.split())} words → **{len(chunks)} chunks** → ~**{est:.0f} min** audio",
                icon="📊")
        if est > 65:
            st.warning("Script 65+ min ka hai — 1 ghante se zyada tool support nahi karta. Chhota karo.")

        if st.button("🎬 Generate Voiceover (1 click)", type="primary"):
            progress = st.progress(0, text="Shuru...")
            status = st.empty()
            wavs, failed = [], 0
            t0 = time.time()
            for i, ch in enumerate(chunks):
                status.write(f"Chunk {i+1}/{len(chunks)} ban raha hai...")
                try:
                    w = cloner.tts_chunk(client, ch, model, voice_id=voice_id)
                    if cloner.wav_duration(w) < 1:
                        raise RuntimeError("empty chunk audio")
                    wavs.append(w)
                except Exception as e:
                    failed += 1
                    status.write(f"⚠️ Chunk {i+1} fail: {str(e)[:120]} — retry...")
                    time.sleep(5)
                    try:
                        w = cloner.tts_chunk(client, ch, model, voice_id=voice_id)
                        wavs.append(w)
                        failed -= 1
                    except Exception as e2:
                        st.error(f"❌ Chunk {i+1} do baara fail: {str(e2)[:200]}")
                        break
                progress.progress((i + 1) / len(chunks),
                                  text=f"Chunk {i+1}/{len(chunks)} ✅")
            if wavs and failed == 0:
                status.write("🔗 Jor raha hun + MP3 bana raha hun...")
                full_wav = cloner.concat_wavs(wavs)
                mp3 = cloner.wav_to_mp3(full_wav, bitrate=bitrate)
                dur = cloner.wav_duration(full_wav)
                # ---- VERIFY: no 0-second files, ever ----
                if dur < 5 or len(mp3) < 10_000:
                    st.error("❌ Output verify nahi hui (khaali/short file) — download nahi dunga. Dobara try karo.")
                else:
                    mins = dur / 60
                    st.success(f"✅ Tayyar! **{mins:.1f} min** audio, {(len(mp3)/1e6):.1f} MB "
                               f"({time.time()-t0:.0f}s mein bana)")
                    st.audio(mp3, format="audio/mp3")
                    fname = f"voiceover_{voice_choice.replace(' ', '_')}_{int(dur//60)}min.mp3"
                    st.download_button("⬇️ Download Full MP3", data=mp3,
                                       file_name=fname, mime="audio/mp3",
                                       help="Poori file — 0 second wali problem nahi hogi, verify ho chuki hai.")
                    # also save server-side
                    os.makedirs(os.path.expanduser("~/.voice-clone-studio/outputs"), exist_ok=True)
                    op = os.path.join(os.path.expanduser("~/.voice-clone-studio/outputs"), fname)
                    with open(op, "wb") as f:
                        f.write(mp3)
            elif failed:
                st.error(f"❌ {failed} chunks fail ho gaye — poori file nahi bani. Dobara try karo.")
