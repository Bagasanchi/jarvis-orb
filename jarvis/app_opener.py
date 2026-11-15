"""Launch known apps without interpolating recognized speech into a shell."""
import os
import subprocess

APP_MAP = {
    "chrome": "chrome", "google chrome": "chrome", "browser": "chrome",
    "edge": "msedge", "microsoft edge": "msedge",
    "vscode": "code", "vs code": "code", "visual studio code": "code",
    "notepad": "notepad", "calculator": "calc", "calc": "calc",
    "explorer": "explorer", "file explorer": "explorer", "terminal": "wt",
    "powershell": "powershell", "task manager": "taskmgr", "paint": "mspaint",
    "word": "winword", "excel": "excel", "spotify": "spotify",
    "discord": "discord", "steam": "steam",
}


def open_app(app_name):
    name = " ".join(app_name.lower().strip().split())
    executable = APP_MAP.get(name)
    if not executable:
        return False, "That app isn't in my supported application list, sir."
    if os.name != "nt":
        return False, "Application launching is currently supported on Windows, sir."
    try:
        result = subprocess.run(["cmd.exe", "/c", "start", "", executable],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            return False, "Windows couldn't launch that application, sir."
        return True, "I've asked Windows to open " + name.title() + ", sir."
    except (OSError, subprocess.SubprocessError):
        return False, "I couldn't launch that application, sir."
