"""
Run Jarvis voice assistant.

Usage:
    python -m jarvis               # Interactive mode (double-clap to wake)
    python -m jarvis --once        # Single-turn test mode
"""

import sys
import os

# Ensure D:/Jarvis is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis.main import main

if __name__ == "__main__":
    main()
