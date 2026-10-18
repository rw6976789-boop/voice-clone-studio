# 🎙️ Voice Cloning Studio

Upload **your own reference voice** + consent clip once → generate long-form
voiceovers (up to 1 hour) in your cloned voice, one click.

Powered by Gemini 3.8 Flash TTS voice replication.

## Use
1. Open the app, add your `GEMINI_API_KEY` to Streamlit Secrets.
2. **My Voice** tab: upload reference voice (30+ sec) + consent clip
   ("I consent to the cloning of my voice for text-to-speech.") → Create.
3. **Generate** tab: upload/paste your script (.md) → Generate → download
   the verified MP3 (duration-checked — never a 0-second file).

## Run locally
```
pip install -r requirements.txt
streamlit run app.py
```
Needs `ffmpeg` installed.
