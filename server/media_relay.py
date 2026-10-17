"""
media_relay.py - Low-latency UDP Media Relay for Voice & Video Streams.

Why UDP for Voice & Video?
TCP retransmits lost packets, which can introduce lag and stutter in real-time audio/video.
UDP sends datagrams directly without blocking. If a frame or audio sample is dropped,
the stream immediately continues with the latest frame without freezing the chat!

How the relay works:
1. Listens on a UDP port (default: 5556).
2. When a client registers or sends a packet, the relay records their (IP, port).
3. Packet structure sent by clients:
   [1 byte Type: 1=Video Frame, 2=Audio Chunk, 3=Heartbeat/Register]
   [1 byte Target Username Length: L]
   [L bytes Target Username]
   [Remaining bytes: Media payload (JPEG image or PCM audio)]
4. The relay inspects the target username and forwards the packet directly to that user's UDP address.
"""

import socket
import threading
from typing import Dict, Tuple

TAG_VIDEO = 1
TAG_AUDIO = 2
TAG_HEARTBEAT = 3


class MediaRelay:
    def __init__(self, host: str = "0.0.0.0", port: int = 5556):
        self.host = host
        self.port = port
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.user_endpoints: Dict[str, Tuple[str, int]] = {}
        self.lock = threading.Lock()
        self.running = False

    def start(self):
        """Starts the UDP relay listening thread."""
        self.udp_sock.bind((self.host, self.port))
        self.running = True
        thread = threading.Thread(target=self._listen_loop, daemon=True, name="MediaRelayThread")
        thread.start()
        print(f"[Media Relay] UDP audio/video relay listening on {self.host}:{self.port}")

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
                if len(data) < 2:
                    continue

                tag = data[0]
                target_len = data[1]
                if len(data) < 2 + target_len:
                    continue

                target_user = data[2:2 + target_len].decode("utf-8", errors="ignore")
                payload = data[2 + target_len:]

                # If this is a registration/heartbeat packet:
                # payload contains the sender's own username
                if tag == TAG_HEARTBEAT:
                    sender_user = payload.decode("utf-8", errors="ignore")
                    with self.lock:
                        self.user_endpoints[sender_user] = addr
                    continue

                # Forward video or audio to the designated recipient
                with self.lock:
                    target_addr = self.user_endpoints.get(target_user)

                if target_addr:
                    self.udp_sock.sendto(data, target_addr)

            except (socket.error, OSError):
                if not self.running:
                    break

    def unregister_user(self, username: str):
        """Removes a user's UDP endpoint when they disconnect."""
        with self.lock:
            self.user_endpoints.pop(username, None)

    def stop(self):
        """Stops the UDP relay."""
        self.running = False
        try:
            self.udp_sock.close()
        except Exception:
            pass
