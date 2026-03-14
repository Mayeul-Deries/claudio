# Claudio

Local voice-to-text desktop app for Windows. Uses OpenAI Whisper (`medium` model) running fully offline — no API calls, no internet required.

## Quick Start

```bash
# 1. Create a virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run (requires admin for global hotkeys)
python main.py
```

Or double-click `run.bat`.

## Hotkeys

| Action | Shortcut |
|---|---|
| Start / Stop recording | `Ctrl+Space` |
| Cancel recording | `Escape` |

## How It Works

1. Press `Ctrl+Space` — the bar expands and starts recording.
2. Speak in French.
3. Press `Ctrl+Space` again — Whisper transcribes your speech.
4. Text is copied to clipboard. If a text field is focused, it auto-pastes.

## Notes

- First launch downloads the Whisper `medium` model (~1.5 GB).
- Requires a working microphone.
- Run as administrator for global hotkey support.
