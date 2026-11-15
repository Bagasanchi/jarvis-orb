"""Jarvis voice assistant. Imports stay light for demos and tooling."""

def __getattr__(name):
    if name == "JarvisAssistant":
        from jarvis.main import JarvisAssistant
        return JarvisAssistant
    raise AttributeError(name)
