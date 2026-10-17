"""
protocol.py - Custom framing & serialization protocol for the chat application.

Why length-prefixed framing?
TCP is a byte-stream protocol without built-in message boundaries. If two messages
are sent rapidly, TCP can deliver them together in a single read (framing/gluing),
or split a single large message across multiple read calls (fragmentation).

To solve this cleanly, we prefix every packet with a 4-byte Big-Endian unsigned
integer indicating the payload size in bytes:
[ 4-byte Length (N) ] [ N bytes of UTF-8 encoded JSON data ]
"""

import json
import struct
import socket
from typing import Optional, Any, Dict

# Header length: 4 bytes for unsigned int (up to 4GB payload)
HEADER_SIZE = 4
HEADER_FORMAT = "!I"  # Network byte order (Big-Endian), 32-bit unsigned int

# Standard Packet Types
TYPE_REGISTER = "register"          # Client registers username
TYPE_USER_LIST = "user_list"        # Broadcast of active online clients
TYPE_ROOM_LIST = "room_list"        # Broadcast of active chat rooms
TYPE_MSG = "msg"                    # Chat message (Group room or Private 1-to-1)
TYPE_ROOM_ACTION = "room_action"    # Create, join, or leave a group room
TYPE_FILE = "file"                  # File / Image / Video transfer
TYPE_CALL_SIGNAL = "call_signal"    # Video & audio call signaling (request/accept/decline/end)
TYPE_SYSTEM = "system"              # Server announcements / alerts


def recv_exact(sock: socket.socket, num_bytes: int) -> Optional[bytes]:
    """
    Guarantees reading exactly `num_bytes` from the socket stream.
    Returns bytes when successful, or None if the socket is closed cleanly by peer.
    """
    buffer = bytearray()
    while len(buffer) < num_bytes:
        try:
            chunk = sock.recv(num_bytes - len(buffer))
        except (socket.error, ConnectionResetError, ConnectionAbortedError):
            return None

        if not chunk:
            # Socket closed gracefully by peer
            return None
        buffer.extend(chunk)
    return bytes(buffer)


def send_packet(sock: socket.socket, data: Dict[str, Any]) -> bool:
    """
    Serializes a dictionary to JSON, encodes to UTF-8, prepends 4-byte header,
    and sends completely using sock.sendall().
    Returns True if sent successfully, False otherwise.
    """
    try:
        payload_bytes = json.dumps(data).encode("utf-8")
        header = struct.pack(HEADER_FORMAT, len(payload_bytes))
        sock.sendall(header + payload_bytes)
        return True
    except (socket.error, ConnectionResetError, BrokenPipeError):
        return False


def recv_packet(sock: socket.socket) -> Optional[Dict[str, Any]]:
    """
    Receives a single complete packet from the socket:
    1. Reads the 4-byte header to determine payload length.
    2. Reads the exact payload bytes.
    3. Parses and returns the decoded JSON dictionary.
    Returns None if connection lost or closed.
    """
    try:
        header = recv_exact(sock, HEADER_SIZE)
        if not header:
            return None
        
        payload_length = struct.unpack(HEADER_FORMAT, header)[0]
        payload_bytes = recv_exact(sock, payload_length)
        if not payload_bytes:
            return None
            
        return json.loads(payload_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Corrupted packet
        return None
    except (socket.error, ConnectionResetError, ConnectionAbortedError):
        return None
