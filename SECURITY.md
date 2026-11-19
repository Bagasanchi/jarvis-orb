# Security and privacy

This personal Windows assistant is not a security boundary. Anyone audible to
its microphone can issue supported voice commands. Deleting saved items and cloud
screen capture require local keyboard/mouse approval. Wake phrases do not
authenticate a speaker. Avoid running as administrator.

Publish reviewed source only. Never distribute your working folder: `data/`
contains settings, unencrypted saved memories, optional microphone recordings,
and optional `credentials.json`. All are ignored by Git and excluded from the
Windows build. Environment variables override private credential settings.
Deleting a tracked secret or adding an ignore rule does not remove Git history;
revoke exposed credentials before cleaning history.

Recognition runs locally. Edge TTS sends reply text online. Cloud chat can send
recent conversation and saved facts automatically under the documented routing
rules. Use `use local` and Windows/Piper speech for offline conversations.
Screen capture happens on request. Cloud vision and off-device Ollama require
local approval before capture. Reading saved notes also requires local approval.
Voice commands can be misrecognized, so check visible content before requesting
screen analysis. Cloud URLs should use HTTPS outside the local machine.

Project shortcuts refer only to folders saved through the local panel and fixed
editor choices. Select trusted Godot executables and projects: editor plugins and
Godot tool scripts can execute with your user permissions when a project opens.
The microphone mute control covers wake recognition and voice interruption.
Echo cancellation is an experimental audio feature, not speaker authentication.

Application launches use fixed allowlisted commands. Model text is never
executed as shell code. Filename search does not read matching files. Downloaded
speech models use a fixed HTTPS source with archive size and path checks;
downloads are not independently verified with a pinned checksum.

The Security checks workflow scans tracked text across Git history for potential
secrets, runs Bandit for medium/high severity findings, and audits the dependencies
resolved from requirements.txt with pip-audit. These checks do not prove absence
of vulnerabilities. Dependency ranges are not a reproducible lockfile. Consult
the workflow result for the specific commit being installed.

Do not include credentials, recordings, screenshots or saved data in public bug
reports. If a credential is exposed, revoke it at its provider immediately.
