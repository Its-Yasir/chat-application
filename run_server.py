"""
run_server.py - One-click launcher for the Chat Server.
Run this script in terminal:
    python run_server.py
"""

import sys
import os

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from server.server import ChatServer

if __name__ == "__main__":
    server = ChatServer(host="0.0.0.0", tcp_port=5555, udp_port=5556)
    server.start()
