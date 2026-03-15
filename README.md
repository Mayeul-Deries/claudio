# Claudio

Local voice-to-text desktop app for Windows. Uses OpenAI Whisper (`medium` model) with **GPU Acceleration** running fully offline — no API calls, no internet required.

## Features
- **Instagram-style waveform**: Real-time voice reactivity with smooth animations.
- **Pasted Logic**: Automatically transcribes and pastes into the active window.
- **Background Mode**: Runs silently in the system tray.
- **Auto-Launch**: Can be configured to start with Windows.

## Prerequisites

- **Python 3.10+**
- **FFmpeg**: Required by Whisper for audio processing. [Download here](https://ffmpeg.org/download.html) and add to your PATH.
- **NVIDIA GPU (Optional but Recommended)**: For fast transcription, ensure you have [CUDA](https://developer.nvidia.com/cuda-downloads) installed.

## Installation & Setup

If you are cloning this project for the first time:

1. **Create & Activate Virtual Environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Silent Launcher Setup (Optional)**:
   - The app includes `launcher.vbs` which runs `run.bat` without a visible terminal window.
   - Ensure `run.bat` points to your virtual environment:
     ```batch
     @echo off
     cd /d "%~dp0"
     "venv\Scripts\python.exe" main.py
     ```

## Creating Shortcuts

To easily launch Claudio or make it start with Windows:

### 1. Desktop Shortcut
- Right-click `launcher.vbs` -> **Send to** -> **Desktop (create shortcut)**.
- Rename it to `Claudio`.
- Right-click shortcut -> **Properties** -> **Change Icon** -> Browse to `icon.ico`.

### 2. Launch at Startup
- Press `Win + R`, type `shell:startup`, and press Enter.
- Copy your **Claudio** shortcut into this folder.

## Usage

| Action | Shortcut |
|---|---|
| **Start / Stop recording** | `Ctrl + Space` |
| **Cancel recording** | `Escape` |

1. Press `Ctrl + Space` — the pill bar expands.
2. Speak (optimized for French).
3. Press `Ctrl + Space` again — your speech is transcribed and pasted instantly.

## Troubleshooting

- **Admin Rights**: Some apps block global hotkeys. If `Ctrl+Space` doesn't work, try running `run.bat` as Administrator.
- **Model Download**: On the first run, the Whisper `medium` model (~1.5 GB) will be downloaded automatically.
