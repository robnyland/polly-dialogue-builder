import streamlit as st, boto3, io, os
from tempfile import NamedTemporaryFile

# ── Polly helper ─────────────────────────────────────────────────────
@st.cache_resource
def get_polly_and_voices():
    polly = boto3.client(
        "polly",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )
    voices = polly.describe_voices()["Voices"]
    return polly, voices

def synth_line(polly, text, voice, engine, sample_rate):
    response = polly.synthesize_speech(
        Text=text,
        VoiceId=voice,
        Engine=engine,
        OutputFormat="mp3",
        SampleRate=sample_rate,
    )
    return response['AudioStream'].read()

# ── App UI ───────────────────────────────────────────────────────────
st.title("🗣️ Polly Dialogue Builder")

try:
    polly, all_voices = get_polly_and_voices()
except Exception as e:
    st.error(f"Could not reach Polly → {e}")
    st.stop()

# Global Settings
st.sidebar.header("Global Voice Settings")
voice_quality = st.sidebar.selectbox("Voice Quality", options=["generative", "neural"])
sample_rate = st.sidebar.selectbox("Sample Rate", options=["22050", "48000"])

languages = sorted(set(v["LanguageCode"] for v in all_voices))
selected_language = st.sidebar.selectbox(
    "Language",
    languages,
    index=languages.index("en-US") if "en-US" in languages else 0
)

# Filter voices by language and engine
VOICES = sorted([
    v["Name"] for v in all_voices
    if selected_language == v["LanguageCode"] and voice_quality in v["SupportedEngines"]
])

if not VOICES:
    st.error("No voices available for that language + quality. Try changing options.")
    st.stop()

# Initialize speakers
if "speakers" not in st.session_state:
    st.session_state.speakers = [
        {"voice": VOICES[0], "lines": "Hello!\nHow are you?", "pause": 0},
        {"voice": VOICES[1] if len(VOICES) > 1 else VOICES[0], "lines": "Great, thanks!\nReady for the meeting?", "pause": 0},
    ]

# Speaker configuration
del_idx = None
for i, sp in enumerate(st.session_state.speakers):
    with st.expander(f"Speaker {i+1}", expanded=True):
        if sp["voice"] not in VOICES:
            sp["voice"] = VOICES[0]

        sp["voice"] = st.selectbox(
            "Voice", VOICES,
            index=VOICES.index(sp["voice"]),
            key=f"voice_{i}",
        )

        MAX_CHARS = 3000
        lines = st.text_area(
            "Lines (one per bubble)", sp["lines"],
            key=f"lines_{i}", height=120,
        )
        char_count = len(lines.strip())
        remaining = MAX_CHARS - char_count
        char_text = f"🧮 {remaining} characters left"

        if remaining < 0:
            st.markdown(f"<span style='color:red'>{char_text}</span>", unsafe_allow_html=True)
        else:
            st.caption(char_text)

        sp["lines"] = lines

        sp["pause"] = st.slider(
            "Pause AFTER this speaker (ms)",
            0, 3000, sp["pause"], 100, key=f"pause_{i}",
        )

        if st.button("Remove speaker", key=f"del_{i}"):
            del_idx = i

if del_idx is not None:
    st.session_state.speakers.pop(del_idx)
    st.rerun()

if len(st.session_state.speakers) < 20 and st.button("➕ Add speaker"):
    st.session_state.speakers.append(
        {"voice": VOICES[len(st.session_state.speakers) % len(VOICES)],
         "lines": "", "pause": 0}
    )
    st.rerun()

# ── Generate button ────────────────────────────────────────────────
if st.button("Generate ▶️", type="primary"):
    audio_chunks = []

    for sp in st.session_state.speakers:
        for line in sp["lines"].splitlines():
            if line := line.strip():
                try:
                    audio_chunks.append(synth_line(polly, line, sp["voice"], voice_quality, sample_rate))
                except Exception as e:
                    st.error(f"Polly error with voice “{sp['voice']}” → {e}")
                    st.stop()
        if sp["pause"]:
            # generate silent MP3 bytes (1 sec = 22050 bytes @ ~22kbps)
            silence_ms = sp["pause"]
            silence_bytes = b'\0' * int(22050 * (silence_ms / 1000))
            audio_chunks.append(silence_bytes)

    if not audio_chunks:
        st.warning("No dialogue to synthesise.")
    else:
        with NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            for chunk in audio_chunks:
                tmp.write(chunk)
            tmp.seek(0)
            st.audio(tmp.name, format="audio/mp3")
            st.download_button("💾 Download MP3", tmp, file_name="dialogue.mp3", mime="audio/mpeg")
