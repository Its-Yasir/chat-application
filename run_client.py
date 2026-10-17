"""
run_client.py - One-click launcher for a Client GUI instance.
You can run this multiple times in separate terminals to launch multiple users:
    python run_client.py
"""

import sys
import os

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from client.client_gui import run_app

if __name__ == "__main__":
    run_app()
