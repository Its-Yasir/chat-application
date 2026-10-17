"""
client_core.py - Networking Socket Engine for the Client Application.

Responsibilities:
1. Connects to the TCP chat server (default: 127.0.0.1:5555).
2. Sends the registration packet with desired username.
3. Spawns a dedicated background thread to listen for incoming packets continuously.
4. Reads incoming packets and triggers GUI event callbacks safely.
5. Provides high-level helper functions for sending messages, room actions,
   files (Base64-encoded), and call signals.
"""

import socket
import threading
import os
import base64
import time
from datetime import datetime
from typing import Callable, Optional, Dict, List, Any
import sys

# Ensure common is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.protocol import (
    send_packet,
    recv_packet,
    TYPE_REGISTER,
    TYPE_USER_LIST,
    TYPE_ROOM_LIST,
    TYPE_MSG,
    TYPE_ROOM_ACTION,
    TYPE_FILE,
    TYPE_CALL_SIGNAL,
    TYPE_SYSTEM
)
from common.crypto import encrypt_text, decrypt_text, encrypt_binary, decrypt_binary


class ClientCore:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.username: str = ""
        self.connected = False
        self.running = False

        # Event callbacks (registered by GUI)
        self.on_user_list: Optional[Callable[[List[str]], None]] = None
        self.on_room_list: Optional[Callable[[Dict[str, List[str]]], None]] = None
        self.on_message: Optional[Callable[[str, str, str, str, str], None]] = None
        self.on_file_received: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_call_signal: Optional[Callable[[str, str, str], None]] = None
        self.on_system_message: Optional[Callable[[str], None]] = None
        self.on_registered: Optional[Callable[[str], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

    def connect(self, desired_username: str) -> bool:
        """Connects to server and registers username."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.connected = True
            self.running = True

            # Send registration packet
            reg_pkt = {
                "type": TYPE_REGISTER,
                "username": desired_username.strip()
            }
            if not send_packet(self.sock, reg_pkt):
                return False

            # Start background listener thread
            listener_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name="ClientReceiverThread"
            )
            listener_thread.start()
            return True

        except (socket.error, ConnectionRefusedError) as e:
            self.connected = False
            return False

    def _receive_loop(self):
        """Continuously listens for incoming packets from the server."""
        while self.running and self.sock:
            packet = recv_packet(self.sock)
            if packet is None:
                # Connection dropped
                break

            self._dispatch_packet(packet)

        self.connected = False
        if self.on_disconnected:
            self.on_disconnected()

    def _dispatch_packet(self, packet: Dict[str, Any]):
        """Dispatches an incoming packet to the appropriate registered callback."""
        pkt_type = packet.get("type")

        if pkt_type == TYPE_SYSTEM:
            if packet.get("subtype") == "registered":
                self.username = packet.get("assigned_username", self.username)
                if self.on_registered:
                    self.on_registered(self.username)
            if self.on_system_message:
                self.on_system_message(packet.get("message", ""))

        elif pkt_type == TYPE_USER_LIST:
            users = packet.get("users", [])
            if self.on_user_list:
                self.on_user_list(users)

        elif pkt_type == TYPE_ROOM_LIST:
            rooms = packet.get("rooms", {})
            if self.on_room_list:
                self.on_room_list(rooms)

        elif pkt_type == TYPE_MSG:
            mode = packet.get("mode", "room")
            target = packet.get("target", "General")
            sender = packet.get("sender", "")
            raw_content = packet.get("content", "")
            # Decrypt message content
            content = decrypt_text(raw_content)
            timestamp = packet.get("timestamp", "")
            if self.on_message:
                self.on_message(mode, target, sender, content, timestamp)

        elif pkt_type == TYPE_FILE:
            # Decrypt file payload if encrypted
            raw_b64 = packet.get("data", "")
            if raw_b64:
                try:
                    enc_bytes = base64.b64decode(raw_b64)
                    dec_bytes = decrypt_binary(enc_bytes)
                    packet["data"] = base64.b64encode(dec_bytes).decode("ascii")
                except Exception:
                    pass
            if self.on_file_received:
                self.on_file_received(packet)

        elif pkt_type == TYPE_CALL_SIGNAL:
            sender = packet.get("sender", "")
            action = packet.get("action", "")
            call_type = packet.get("call_type", "video_audio")
            if self.on_call_signal:
                self.on_call_signal(sender, action, call_type)

    # ----------------- Outgoing Actions -----------------

    def send_message(self, mode: str, target: str, content: str) -> bool:
        """Encrypts and sends a text message to a room or a private user."""
        if not self.connected or not self.sock or not content.strip():
            return False

        now_str = datetime.now().strftime("%H:%M")
        # Encrypt plaintext payload with AES-128
        encrypted_content = encrypt_text(content)

        packet = {
            "type": TYPE_MSG,
            "mode": mode,         # "room" or "private"
            "target": target,     # room_name or username
            "content": encrypted_content,
            "timestamp": now_str
        }
        return send_packet(self.sock, packet)

    def send_room_action(self, action: str, room_name: str) -> bool:
        """Creates, joins, or leaves a room."""
        if not self.connected or not self.sock:
            return False
        packet = {
            "type": TYPE_ROOM_ACTION,
            "action": action,     # "create", "join", or "leave"
            "room": room_name
        }
        return send_packet(self.sock, packet)

    def send_file(self, mode: str, target: str, filepath: str) -> bool:
        """Reads a file, encrypts it, encodes in Base64, and sends it to the server."""
        if not self.connected or not self.sock or not os.path.exists(filepath):
            return False

        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)

        # Read binary data
        with open(filepath, "rb") as f:
            file_bytes = f.read()

        # Encrypt file bytes with AES-128
        enc_bytes = encrypt_binary(file_bytes)
        b64_data = base64.b64encode(enc_bytes).decode("ascii")
        now_str = datetime.now().strftime("%H:%M")

        packet = {
            "type": TYPE_FILE,
            "mode": mode,
            "target": target,
            "filename": filename,
            "filesize": filesize,
            "timestamp": now_str,
            "data": b64_data
        }
        return send_packet(self.sock, packet)

    def send_call_signal(self, action: str, target: str, call_type: str = "video_audio") -> bool:
        """Sends a call signaling packet (request, accept, decline, end)."""
        if not self.connected or not self.sock:
            return False

        packet = {
            "type": TYPE_CALL_SIGNAL,
            "action": action,      # "request", "accept", "decline", "end"
            "target": target,
            "call_type": call_type
        }
        return send_packet(self.sock, packet)

    def disconnect(self):
        """Closes the client socket gracefully."""
        self.running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
