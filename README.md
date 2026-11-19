# Jarvis Orb

A desktop voice assistant with an animated network sphere, local Ollama chat,
optional cloud AI, and sentence-streamed speech. Say **Hey Jarvis** or press
**Space / Enter** to begin. Clap activation has been removed.

## Mac download

[Download Jarvis for macOS](https://github.com/Bagasanchi/jarvis-orb/raw/refs/heads/main/downloads/Jarvis-macOS.zip). Install Python 3.12
with Tk from python.org, unzip the package into a writable folder, then open
Terminal in the extracted Jarvis folder and run `./Start_Jarvis.command`.
The first launch installs dependencies into a private virtual environment.
Use the same command for subsequent launches. In Settings, download the
English speech model and select your microphone. For local AI, install
Ollama for macOS and run `ollama pull qwen3.5:2b`. Grant microphone access
when prompted and screen recording access only if you use screen analysis.

The launcher stores settings and memories in `~/Library/Application Support/Jarvis`.
Mac users can select Edge speech (online) or configure Piper separately.
Windows tray, app shortcuts, Windows voice and media keys are Windows features.
The Mac package is an unsigned source distribution and needs live Mac testing.
To recreate it, run `python scripts/build_macos.py`.

## Windows setup

Use Python 3.12 or newer with tkinter. Python 3.14 is tested locally.
Double-click `Setup_Jarvis.cmd`, then `Start_Jarvis_Face.cmd`, or run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m jarvis.setup --gui
.\.venv\Scripts\python.exe run_jarvis_face.py
```

Settings opens on the first graphical launch. Select and test a microphone.
Use the Download button to install the official English Vosk model if needed.
Install [Ollama](https://ollama.com/download/windows), start it, and run
`ollama pull qwen3.5:2b`. Built-in actions do not require an AI model.

## Controls

| Control | Action |
| --- | --- |
| Hey Jarvis | Wake from standby using local Vosk recognition |
| Space / Enter | Begin, interrupt a reply, or retry after an input error |
| F2 | Settings; conversation input pauses while Settings is open |
| F3 | Conversation history, typed requests, corrections, project shortcuts |
| F4 | Hide the orb to the Windows tray (minimize if tray unavailable) |
| M | Mute/unmute the microphone; typed requests still work |
| T | Switch cyan / amber palette |
| Esc / close window | Quit |
| Go to sleep / stop listening | Return to standby |

After waking, conversation continues without another wake phrase each turn.
Change or disable the wake phrase in Settings. Keyboard controls require focus.

## Commands

| Say | Action |
| --- | --- |
| Open notepad / launch calculator | Launch an allowlisted app |
| Volume up / volume down / mute | Send Windows volume keys |
| Play music / pause music / play pause | Send Windows' play/pause toggle |
| Next track / previous track | Send a media key |
| Set a timer for five minutes | Start a timer |
| List timers / cancel timer one | Inspect or cancel timers |
| Take a note buy milk / read my notes | Save or read local notes |
| Remember that I study Japanese | Persist a fact for future conversations |
| What do you remember? / forget 1 | List or delete saved facts by ID |
| Delete note 2 | Delete a note by ID |
| Forget everything | Delete saved facts, notes, and current chat history |
| Find file homework | Search filenames under the configured folder |
| What time is it? | Read the local clock |
| What is the weather in Tokyo? | Fetch requested weather |
| Explain my screen | Analyze a screenshot with a configured local vision model |
| Use cloud explain my screen | Explicitly send a screenshot to configured cloud vision |

Play/pause is a toggle, not a guaranteed media state. Volume uses Windows key
increments. Timers beep and display a notice; they do not survive a restart.
Filename searches return up to five matches, with a 20,000-file/three-second
scan budget. Symlink/junction directories are skipped; file contents are not
read. Recognized speech is never executed as an arbitrary shell command.

## Streaming and interruption

Text streams from Ollama or the gateway. Jarvis speaks complete sentences while
later text is generated. Each sentence is synthesized before playback; this is
sentence streaming rather than raw audio streaming.

**Speakers mode is the default.** Experimental echo cancellation uses the actual
playback audio, estimates acoustic delay, and adapts a filter for room reflections.
Say **Jarvis stop** during a reply. Natural interruption remains an optional
setting. This is not guaranteed across every room, volume level, and audio driver;
live testing on your laptop is necessary. If it triggers falsely, disable echo
cancellation in F2 to restore half-duplex operation and use **Space/Enter**.
If playback cannot supply a reference, voice interruption fails closed. Jarvis
waits 0.4 seconds for the remaining speaker echo before listening again.

In **headphones mode**, say **Jarvis stop**, **stop talking**, **stop Jarvis**,
or **stop** to interrupt. Space/Enter also cancels speech preparation and queued text. A network request
may remain open until its read timeout, but cancelled output cannot play in a
later turn. Interrupted conversation history marks the response as incomplete.

**Natural interruption** is experimental. Say a correction of at least three
words. Jarvis stops and passes buffered microphone audio into its next recognition
turn. Speakers use the playback-reference filter; headphones do not need it.
Background voices or difficult acoustics can still cause false triggers.

## Conversation, tray and project shortcuts

F3 opens an in-memory conversation panel. Type a request and press Enter, or use
Edit last request to correct and resend recognized text. Resending does not undo
an action already performed. History is limited to the last 100 exchanges and
is not written to disk. The panel also shows Ollama availability, cloud configuration
(not a cloud connectivity guarantee), last attempted AI backend, voice, and echo status.

On Windows, right-click the Jarvis tray icon to show the orb or conversation
panel, mute/unmute the microphone, or quit. Closing the orb hides it when the tray
is available; Esc quits. If Windows cannot create a tray icon, closing quits and
F4 minimizes normally. Muting disables microphone input, including wake phrases
and voice interruption, while typed requests remain available.

Choose Add project shortcut in F3, give the project a nickname, select its folder,
and choose explorer, vscode or godot. Then say “open my Jarvis” or “open my Jarvis
in VS Code.” Select your trusted Godot .exe in F2 before launching Godot projects.
Shortcuts are saved privately in data/workspaces.json. Only saved folder names
and fixed editor arguments are accepted; voice cannot register executables.

Deleting saved items or all memories now requires a local confirmation. Sending
a screenshot to cloud AI also requires confirmation before capture; the dialog
shows the destination host. Only a click or keyboard response can approve, never
spoken “yes” or model output. Console mode requires typing YES. Missing UI, denial,
timeout or shutdown cancels approval.
Interrupting a reply also invalidates its pending approval. Confirmed “forget
everything” clears saved items, AI history, the visible transcript and correction
input. Replies from older turns cannot restore that cleared conversation.

## Voices

- **auto**: Edge TTS online, falling back to installed Windows offline speech.
- **edge**: Edge TTS only. `JARVIS_TTS_VOICE` selects the voice where supported.
- **windows**: installed Windows speech offline; available voices depend on the PC.
- **piper**: optional `piper-tts` executable and an existing `.onnx` voice model.
  Install separately, select the model in Settings, and check its voice license.

## Local AI, cloud and privacy

Everyday chat uses Ollama. Coding/research keywords and longer questions can
route to an optional OpenAI-compatible gateway. Automatic routing falls back on
early failure; these rules do not measure difficulty. A failed partial answer
is not repeated through a different backend.

Say **use local ...** to prevent cloud fallback, or **use cloud ...** to force
the gateway. Configure your own credentials in PowerShell:

```powershell
$env:JARVIS_CLOUD_URL = "http://127.0.0.1:31415/v1"
$env:JARVIS_CLOUD_API_KEY = "YOUR_OWN_KEY"
$env:JARVIS_CLOUD_MODEL = "auto"
```

`.env.example` documents overrides; `.env` files are not loaded automatically.
Only explicit remember/note requests are stored in SQLite. Chat stays in RAM.
Saved facts are supplied to AI, including cloud AI when cloud routing is used.
Notes are not injected automatically. Local data is not encrypted.

Source installs save private settings, memories and optional test recordings in
`data/`. Packaged installs use `%LOCALAPPDATA%\Jarvis`. `JARVIS_DATA_DIR` overrides
this. These files are excluded from version control and packaging.

Optional private cloud credentials live in `data/credentials.json` with keys
`cloud_url`, `cloud_api_key`, and `cloud_model`; environment variables override
them. Never share that file or your entire working folder. See [SECURITY.md](SECURITY.md)
for the privacy model, limitations, and automated security checks.

Screen analysis captures only when requested, keeps the image in memory, and
uses local Ollama by default. Select an installed vision-capable model in
Settings; ordinary chat models are not assumed to support images. Cloud vision
also requires `JARVIS_CLOUD_VISION_MODEL` and the explicit use-cloud command.
An Ollama server configured on another machine also requires local approval
before capture. Jarvis shows its host and port. On-device Ollama screen analysis
stays hands-free. Reading saved notes aloud requires one local approval.

Recognition and wake phrases are local. Edge TTS sends speech text online,
weather uses wttr.in, and cloud chat sends recent history plus saved facts.
For offline chat, use an installed local model, use-local routing, and a
Windows/Piper voice. Model downloads require internet.

## Diagnostics

F2 Settings provides input selection, a level meter, and a microphone test.
The meter saves no audio. Record & play explicitly saves `data/mic-test.wav`.
You can also run:

```powershell
python -m jarvis.setup --check
python -m jarvis.setup --list-devices
python -m jarvis.setup --test-mic
```

If PortAudio fails, check Windows microphone permissions and try another device
or host API. WASAPI selection enables shared-mode sample-rate conversion.
After changing Settings, press Space to retry an input error. Hardware access
and speech accuracy still require testing in the actual Windows session.

## Tests and Windows packaging

```powershell
python -m unittest discover -s tests -v
python run_jarvis_face.py --demo --seconds 3
```

Tests cover routing, sentence streaming, cancellation, later replies, memory,
timers, search scope, wake phrases, audio handoff, screen privacy and rendering.
Most audio/AI services are mocked; real recognition and echo need live testing.

GitHub Actions tests Windows/Linux on Python 3.12/3.14. The Windows package
workflow runs manually or on a `v*` tag and uploads a Jarvis-Windows artifact.
Build locally with:

```powershell
python -m pip install pyinstaller
python scripts/build_windows.py
```

The build uses allowlisted source and replaces configuration with the public
`config.example.py`. Private keys, models, memories, backups and cached speech
are never copied. Distribute the entire `dist/Jarvis` folder, including
`Jarvis.exe`. Models and Ollama are set up separately. The build is unsigned.

## Source

`face.py`: orb and worker; `brain.py`: AI routing and streaming; `tts.py`: speech;
`stt.py`, `audio.py`, `wake.py`, `interruption.py`: input; `desktop.py`: actions;
`memory.py`: saved items; `screen.py`: on-demand vision; `setup.py`: Settings.
