"""
server.py - Central Multithreaded TCP Server for Real-Time Multi-User Chat.

Key Responsibilities:
1. Listens on TCP port 5555 for incoming client connections.
2. Spawns an independent worker thread for each connected client.
3. Maintains a thread-safe registry of connected users and chat rooms using threading.Lock.
4. Routes messages:
   - Room broadcasts (forwarded to all users in that specific chat room)
   - Private 1-to-1 messages (forwarded directly to recipient)
   - File/media transfers (forwarded to target user or room)
   - Call signaling (initiating, accepting, declining, ending video/audio calls)
5. Automatically broadcasts updated active user lists and room lists whenever
   a client connects, disconnects, or modifies rooms.
6. Runs the UDP MediaRelay for high-performance audio/video streaming.
"""

import socket
import threading
import sys
import os
from typing import Dict, Set, Optional

# Add parent directory to path so common and server modules can be imported
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
from server.media_relay import MediaRelay


class ChatServer:
    def __init__(self, host: str = "0.0.0.0", tcp_port: int = 5555, udp_port: int = 5556):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port

        # Networking sockets
        self.tcp_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Thread-safe data stores
        self.lock = threading.Lock()
        # username -> socket.socket
        self.clients: Dict[str, socket.socket] = {}
        # room_name -> set of usernames
        self.rooms: Dict[str, Set[str]] = {
            "General": set(),
            "Lounge": set(),
        }
        # username -> set of joined room_names
        self.user_rooms: Dict[str, Set[str]] = {}

        # Media UDP relay
        self.media_relay = MediaRelay(host=self.host, port=self.udp_port)
        self.running = False

    def start(self):
        """Starts the chat server and listens for incoming connections."""
        self.tcp_server_sock.bind((self.host, self.tcp_port))
        self.tcp_server_sock.listen(50)
        self.running = True

        # Start the media relay in background
        self.media_relay.start()

        print("=" * 60)
        print(f"[Server] TCP Chat Server running on {self.host}:{self.tcp_port}")
        print(f"[Server] UDP Media Relay running on {self.host}:{self.udp_port}")
        print(f"[Server] Ready for clients on localhost or LAN/Wi-Fi!")
        print("=" * 60)

        try:
            while self.running:
                try:
                    client_sock, client_addr = self.tcp_server_sock.accept()
                except (OSError, socket.error):
                    if not self.running:
                        break
                    continue
                print(f"[Server] New connection from {client_addr[0]}:{client_addr[1]}")

                # Spawn a dedicated worker thread for each connecting client
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    daemon=True
                )
                thread.start()
        except KeyboardInterrupt:
            print("\n[Server] Shutting down server...")
        finally:
            self.stop()

    def _handle_client(self, client_sock: socket.socket, client_addr):
        """Dedicated worker thread for handling a single client connection."""
        username: Optional[str] = None

        try:
            # 1. First packet must be registration: {"type": "register", "username": "..."}
            init_packet = recv_packet(client_sock)
            if not init_packet or init_packet.get("type") != TYPE_REGISTER:
                client_sock.close()
                return

            raw_username = init_packet.get("username", "").strip()
            if not raw_username:
                raw_username = f"User_{client_addr[1]}"

            # Ensure unique username
            with self.lock:
                username = raw_username
                count = 1
                while username in self.clients:
                    username = f"{raw_username}_{count}"
                    count += 1

                self.clients[username] = client_sock
                self.user_rooms[username] = {"General"}
                self.rooms["General"].add(username)

            print(f"[Server] User registered: '{username}' ({client_addr[0]}:{client_addr[1]})")

            # Acknowledge registration with final assigned username
            send_packet(client_sock, {
                "type": TYPE_SYSTEM,
                "subtype": "registered",
                "assigned_username": username,
                "message": f"Welcome {username}! Connected to server."
            })

            # Broadcast updated user list and rooms to all clients
            self._broadcast_user_list()
            self._broadcast_room_list()
            self._broadcast_to_room("General", {
                "type": TYPE_SYSTEM,
                "room": "General",
                "message": f"👋 {username} joined #General."
            }, exclude_user=username)

            # 2. Main packet receiving loop for this client
            while self.running:
                packet = recv_packet(client_sock)
                if packet is None:
                    # Client disconnected or error occurred
                    break

                self._process_client_packet(username, packet)

        except (socket.error, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if username:
                self._disconnect_client(username)
            try:
                client_sock.close()
            except Exception:
                pass

    def _process_client_packet(self, sender: str, packet: dict):
        """Processes and routes an incoming packet from a registered client."""
        pkt_type = packet.get("type")

        # ----------------- Chat Message -----------------
        if pkt_type == TYPE_MSG:
            mode = packet.get("mode", "room")
            target = packet.get("target", "General")
            content = packet.get("content", "")
            timestamp = packet.get("timestamp", "")

            out_packet = {
                "type": TYPE_MSG,
                "mode": mode,
                "target": target,
                "sender": sender,
                "content": content,
                "timestamp": timestamp
            }

            if mode == "private":
                # Route direct message to the recipient and echo back to sender
                self._send_to_user(target, out_packet)
                self._send_to_user(sender, out_packet)
            else:
                # Group message: broadcast to all members of target room
                self._broadcast_to_room(target, out_packet)

        # ----------------- Room Actions -----------------
        elif pkt_type == TYPE_ROOM_ACTION:
            action = packet.get("action")
            room_name = packet.get("room", "").strip()
            if not room_name:
                return

            if action == "create":
                with self.lock:
                    if room_name not in self.rooms:
                        self.rooms[room_name] = set()
                    self.rooms[room_name].add(sender)
                    self.user_rooms.setdefault(sender, set()).add(room_name)
                self._broadcast_room_list()
                self._send_to_user(sender, {
                    "type": TYPE_SYSTEM,
                    "message": f"Created and joined room #{room_name}"
                })

            elif action == "join":
                with self.lock:
                    if room_name not in self.rooms:
                        self.rooms[room_name] = set()
                    self.rooms[room_name].add(sender)
                    self.user_rooms.setdefault(sender, set()).add(room_name)
                self._broadcast_room_list()
                self._broadcast_to_room(room_name, {
                    "type": TYPE_SYSTEM,
                    "room": room_name,
                    "message": f"👋 {sender} joined #{room_name}."
                }, exclude_user=sender)

            elif action == "leave":
                with self.lock:
                    if room_name in self.rooms:
                        self.rooms[room_name].discard(sender)
                    if sender in self.user_rooms:
                        self.user_rooms[sender].discard(room_name)
                self._broadcast_room_list()
                self._broadcast_to_room(room_name, {
                    "type": TYPE_SYSTEM,
                    "room": room_name,
                    "message": f"🚪 {sender} left #{room_name}."
                })

        # ----------------- File / Media Sharing -----------------
        elif pkt_type == TYPE_FILE:
            # Relay file packet to private user or room members
            mode = packet.get("mode", "room")
            target = packet.get("target", "General")
            packet["sender"] = sender

            if mode == "private":
                self._send_to_user(target, packet)
                self._send_to_user(sender, packet)
            else:
                self._broadcast_to_room(target, packet)

        # ----------------- Video / Voice Call Signaling -----------------
        elif pkt_type == TYPE_CALL_SIGNAL:
            target = packet.get("target")
            packet["sender"] = sender
            # Route call signals directly between the two users
            if target:
                self._send_to_user(target, packet)

    def _send_to_user(self, username: str, packet: dict) -> bool:
        """Sends a packet to a specific user's socket."""
        with self.lock:
            sock = self.clients.get(username)
        if sock:
            return send_packet(sock, packet)
        return False

    def _broadcast_to_room(self, room_name: str, packet: dict, exclude_user: Optional[str] = None):
        """Sends a packet to all members of a given room."""
        with self.lock:
            member_usernames = list(self.rooms.get(room_name, set()))
            sockets = [
                self.clients[u] for u in member_usernames
                if u != exclude_user and u in self.clients
            ]

        for sock in sockets:
            send_packet(sock, packet)

    def _broadcast_user_list(self):
        """Sends the current list of active online users to all clients."""
        with self.lock:
            users = sorted(list(self.clients.keys()))
            all_sockets = list(self.clients.values())

        packet = {"type": TYPE_USER_LIST, "users": users}
        for sock in all_sockets:
            send_packet(sock, packet)

    def _broadcast_room_list(self):
        """Sends the list of active rooms and their member counts to all clients."""
        with self.lock:
            room_info = {
                r_name: list(members) for r_name, members in self.rooms.items()
            }
            all_sockets = list(self.clients.values())

        packet = {"type": TYPE_ROOM_LIST, "rooms": room_info}
        for sock in all_sockets:
            send_packet(sock, packet)

    def _disconnect_client(self, username: str):
        """Cleans up all state when a client disconnects."""
        print(f"[Server] User disconnected: '{username}'")
        with self.lock:
            self.clients.pop(username, None)
            user_joined_rooms = self.user_rooms.pop(username, set())
            for room in user_joined_rooms:
                if room in self.rooms:
                    self.rooms[room].discard(username)

        self.media_relay.unregister_user(username)
        self._broadcast_user_list()
        self._broadcast_room_list()

        # Announce departure in previously joined rooms
        for room in user_joined_rooms:
            self._broadcast_to_room(room, {
                "type": TYPE_SYSTEM,
                "room": room,
                "message": f"🚪 {username} disconnected."
            })

    def stop(self):
        """Stops the TCP server and closes all sockets."""
        self.running = False
        self.media_relay.stop()
        try:
            self.tcp_server_sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    server = ChatServer()
    server.start()
