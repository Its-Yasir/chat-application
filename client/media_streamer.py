"""
media_streamer.py - Real-Time Video & Voice Calling Engine for the Client.

Features:
1. Video Streaming: Captures webcam frames using OpenCV (`cv2`) if available,
   or synthesizes real-time live animated frames (PPM / JPEG).
   Uses native Tkinter PhotoImage (with PPM) or Pillow ImageTk for zero-dependency playback!
2. Audio Streaming: Streams live microphone audio and plays received audio
   via `sounddevice`.
3. Low-Latency UDP Relay: Streams video & audio over UDP directly through
   the server MediaRelay on port 5556 without blocking TCP chat.
4. Call Window: Clean floating Tkinter dialog with remote video screen,
   local camera preview, audio controls (Mute Mic, Camera Off, End Call).
"""

import socket
import threading
import time
import io
import math
from typing import Optional, Callable, Any
import tkinter as tk
from tkinter import ttk, messagebox

# Optional media imports with graceful fallbacks
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    CV2_AVAILABLE = False

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    ImageTk = None
    ImageDraw = None
    PIL_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

# Protocol Tags matching server/media_relay.py
TAG_VIDEO = 1
TAG_AUDIO = 2
TAG_HEARTBEAT = 3

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_BLOCK_SIZE = 1024


class MediaStreamer:
    def __init__(self, relay_host: str = "127.0.0.1", relay_port: int = 5556,
                 my_username: str = "", peer_username: str = "",
                 on_call_ended: Optional[Callable[[], None]] = None):
        self.relay_host = relay_host
        self.relay_port = relay_port
        self.my_username = my_username
        self.peer_username = peer_username
        self.on_call_ended = on_call_ended

        self.running = False
        self.udp_sock: Optional[socket.socket] = None

        # Call window GUI
        self.call_window: Optional[tk.Toplevel] = None
        self.remote_video_label: Optional[tk.Label] = None
        self.local_video_label: Optional[tk.Label] = None
        self.status_label: Optional[tk.Label] = None

        # Camera & Audio state
        self.cap: Optional[Any] = None
        self.mic_muted = False
        self.video_muted = False

        # Persistent PhotoImage references to avoid Python garbage collection
        self._current_remote_img = None
        self._current_local_img = None

    def start_call(self, parent_window: tk.Tk):
        """Initializes the UDP socket, opens the Call Window, and starts stream threads."""
        self.running = True
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Bind to any available local port
        self.udp_sock.bind(("0.0.0.0", 0))

        # Register endpoint with media relay
        self._send_heartbeat()

        # Build Call Window UI
        self._create_call_window(parent_window)

        # Start Receiver Thread
        recv_thread = threading.Thread(target=self._recv_loop, daemon=True, name="MediaRecvThread")
        recv_thread.start()

        # Start Video Capture & Sender Thread
        video_thread = threading.Thread(target=self._video_send_loop, daemon=True, name="VideoSendThread")
        video_thread.start()

        # Start Audio Capture & Sender Thread
        audio_thread = threading.Thread(target=self._audio_send_loop, daemon=True, name="AudioSendThread")
        audio_thread.start()

    def _send_heartbeat(self):
        """Informs the server media relay of our UDP port."""
        if not self.udp_sock:
            return
        # Packet: [TAG_HEARTBEAT (1B)][Target Len=0 (1B)][Sender Username]
        my_bytes = self.my_username.encode("utf-8")
        packet = bytes([TAG_HEARTBEAT, 0]) + my_bytes
        try:
            self.udp_sock.sendto(packet, (self.relay_host, self.relay_port))
        except Exception:
            pass

    def _create_call_window(self, parent: tk.Tk):
        """Constructs the floating call dialog window."""
        self.call_window = tk.Toplevel(parent)
        self.call_window.title(f"Live Call - {self.peer_username}")
        self.call_window.geometry("640x520")
        self.call_window.minsize(580, 480)
        self.call_window.configure(bg="#1E1E2E")
        self.call_window.protocol("WM_DELETE_WINDOW", self.end_call)

        # Header Info
        header_frame = tk.Frame(self.call_window, bg="#181825", height=45)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header_frame,
            text=f"📞 Live Call with @{self.peer_username}",
            font=("Segoe UI", 12, "bold"),
            bg="#181825",
            fg="#CDD6F4"
        )
        title_lbl.pack(side=tk.LEFT, padx=15, pady=8)

        self.status_label = tk.Label(
            header_frame,
            text="🟢 Audio & Video Active",
            font=("Segoe UI", 10),
            bg="#181825",
            fg="#A6E3A1"
        )
        self.status_label.pack(side=tk.RIGHT, padx=15, pady=8)

        # Video Displays Container
        video_container = tk.Frame(self.call_window, bg="#11111B")
        video_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Remote Video Frame (Main view)
        remote_frame = tk.Frame(video_container, bg="#181825", bd=2, relief=tk.SOLID)
        remote_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        remote_title = tk.Label(remote_frame, text=f"📹 Remote Video Feed (@{self.peer_username})",
                                font=("Segoe UI", 9, "bold"), bg="#181825", fg="#BAC2DE")
        remote_title.pack(side=tk.TOP, pady=4)

        self.remote_video_label = tk.Label(remote_frame, bg="#000000", text="Connecting to peer video...",
                                           fg="#6C7086", font=("Segoe UI", 11))
        self.remote_video_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Local Video Preview (Self view)
        local_frame = tk.Frame(video_container, bg="#181825", bd=2, relief=tk.SOLID, width=200)
        local_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=5, pady=5)

        local_title = tk.Label(local_frame, text="📷 My Camera Preview",
                               font=("Segoe UI", 9, "bold"), bg="#181825", fg="#BAC2DE")
        local_title.pack(side=tk.TOP, pady=4)

        self.local_video_label = tk.Label(local_frame, bg="#000000", text="Camera loading...",
                                          fg="#6C7086", font=("Segoe UI", 9), width=24, height=14)
        self.local_video_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Bottom Control Bar
        control_bar = tk.Frame(self.call_window, bg="#181825", height=60)
        control_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)

        self.mute_mic_btn = tk.Button(
            control_bar,
            text="🎙️ Mic On",
            font=("Segoe UI", 10, "bold"),
            bg="#313244",
            fg="#CDD6F4",
            activebackground="#45475A",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=6,
            command=self._toggle_mic
        )
        self.mute_mic_btn.pack(side=tk.LEFT, padx=20, pady=10)

        self.mute_video_btn = tk.Button(
            control_bar,
            text="📹 Camera On",
            font=("Segoe UI", 10, "bold"),
            bg="#313244",
            fg="#CDD6F4",
            activebackground="#45475A",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=6,
            command=self._toggle_video
        )
        self.mute_video_btn.pack(side=tk.LEFT, padx=10, pady=10)

        end_btn = tk.Button(
            control_bar,
            text="🔴 End Call",
            font=("Segoe UI", 10, "bold"),
            bg="#F38BA8",
            fg="#11111B",
            activebackground="#E78284",
            activeforeground="#11111B",
            relief=tk.FLAT,
            padx=18,
            pady=6,
            command=self.end_call
        )
        end_btn.pack(side=tk.RIGHT, padx=20, pady=10)

    def _toggle_mic(self):
        self.mic_muted = not self.mic_muted
        if self.mic_muted:
            self.mute_mic_btn.config(text="🔇 Mic Muted", bg="#F38BA8", fg="#11111B")
        else:
            self.mute_mic_btn.config(text="🎙️ Mic On", bg="#313244", fg="#CDD6F4")

    def _toggle_video(self):
        self.video_muted = not self.video_muted
        if self.video_muted:
            self.mute_video_btn.config(text="🚫 Camera Off", bg="#F38BA8", fg="#11111B")
        else:
            self.mute_video_btn.config(text="📹 Camera On", bg="#313244", fg="#CDD6F4")

    # ----------------- Video Loop -----------------

    def _video_send_loop(self):
        """Captures local camera or synthetic pattern, sends to peer, and renders preview."""
        cap = None
        if CV2_AVAILABLE:
            try:
                cap = cv2.VideoCapture(0)
                ret, _ = cap.read() if cap.isOpened() else (False, None)
                if not ret and cap:
                    cap.release()
                    cap = None
            except Exception:
                cap = None

        frame_idx = 0
        target_bytes = self.peer_username.encode("utf-8")
        target_len = len(target_bytes)

        while self.running:
            start_time = time.time()

            if self.video_muted:
                frame_data = self._create_synthetic_ppm(frame_idx, muted=True)
            elif cap and cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    frame = cv2.resize(frame, (160, 120))
                    # Convert to PPM format for universal zero-dependency display
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, _ = frame_rgb.shape
                    header = f"P6\n{w} {h}\n255\n".encode("ascii")
                    frame_data = header + frame_rgb.tobytes()
                else:
                    frame_data = self._create_synthetic_ppm(frame_idx)
            else:
                frame_data = self._create_synthetic_ppm(frame_idx)

            # Send video packet over UDP to relay:
            # [TAG_VIDEO (1B)][target_len (1B)][target_bytes][frame_data]
            if self.udp_sock and frame_data:
                packet = bytes([TAG_VIDEO, target_len]) + target_bytes + frame_data
                try:
                    self.udp_sock.sendto(packet, (self.relay_host, self.relay_port))
                except Exception:
                    pass

                # Update local preview
                self._update_local_preview(frame_data)

            frame_idx += 1
            # Maintain ~12-15 FPS for smooth video without network overload
            elapsed = time.time() - start_time
            sleep_duration = max(0.01, (1.0 / 12.0) - elapsed)
            time.sleep(sleep_duration)

        if cap and cap.isOpened():
            cap.release()

    def _create_synthetic_ppm(self, frame_idx: int, muted: bool = False) -> bytes:
        """
        Creates an animated live video avatar with user initials and bouncing audio waves.
        Renders via Pillow (when available) or raw PPM, displaying seamlessly in Tkinter.
        """
        width, height = 320, 240

        if PIL_AVAILABLE:
            img = Image.new("RGB", (width, height), color=(24, 24, 37))
            draw = ImageDraw.Draw(img)

            if muted:
                draw.text((width // 2 - 50, height // 2 - 10), "Camera Off", fill=(108, 112, 134))
                buf = io.BytesIO()
                img.save(buf, format="PPM")
                return buf.getvalue()

            # Dynamic pulsing circle avatar
            t = frame_idx * 0.18
            cx, cy = width // 2, height // 2 - 25
            pulse = int(5 * math.sin(t))
            radius = 42 + pulse

            # Glowing outer ring
            draw.ellipse([cx - radius - 3, cy - radius - 3, cx + radius + 3, cy + radius + 3],
                         outline=(137, 180, 250), width=3)
            # Inner avatar fill
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                         fill=(49, 50, 68))

            # Initial letter
            initial = (self.my_username[:1] or "U").upper()
            draw.text((cx - 8, cy - 12), initial, fill=(205, 214, 244))

            # Username label
            user_lbl = f"@{self.my_username}"
            draw.text((cx - len(user_lbl) * 4, cy + radius + 12), user_lbl, fill=(205, 214, 244))

            # Bouncing audio equalizer bars below name
            bar_y = cy + radius + 36
            for i in range(7):
                bar_x = cx - 36 + (i * 12)
                bar_h = int(6 + 14 * abs(math.sin(t + i * 0.8)))
                draw.rounded_rectangle([bar_x, bar_y - bar_h, bar_x + 6, bar_y + bar_h],
                                       radius=2, fill=(166, 227, 161))

            # Status notice at bottom
            draw.text((cx - 72, height - 22), "🟢 Live Stream Active", fill=(166, 227, 161))

            buf = io.BytesIO()
            img.save(buf, format="PPM")
            return buf.getvalue()

        # Fallback if Pillow is absent: basic PPM
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        pixels = bytearray(width * height * 3)
        return header + bytes(pixels)

    def _update_local_preview(self, frame_data: bytes):
        """Safely updates local camera preview on Tkinter UI."""
        if not self.call_window or not frame_data:
            return

        try:
            # Native Tkinter PhotoImage accepts raw PPM data
            photo = tk.PhotoImage(data=frame_data)

            def _apply():
                if self.local_video_label and self.local_video_label.winfo_exists():
                    self.local_video_label.configure(image=photo, text="")
                    self._current_local_img = photo

            if self.call_window.winfo_exists():
                self.call_window.after(0, _apply)
        except Exception:
            pass

    # ----------------- Audio Loop -----------------

    def _audio_send_loop(self):
        """Captures microphone input and sends PCM blocks over UDP."""
        if not SOUNDDEVICE_AVAILABLE:
            return

        target_bytes = self.peer_username.encode("utf-8")
        target_len = len(target_bytes)

        try:
            with sd.RawInputStream(samplerate=AUDIO_SAMPLE_RATE, blocksize=AUDIO_BLOCK_SIZE,
                                   channels=AUDIO_CHANNELS, dtype="int16") as stream:
                while self.running:
                    data, overflowed = stream.read(AUDIO_BLOCK_SIZE)
                    if self.mic_muted or not self.running:
                        time.sleep(0.05)
                        continue

                    # Send audio packet: [TAG_AUDIO (1B)][target_len (1B)][target_bytes][data]
                    packet = bytes([TAG_AUDIO, target_len]) + target_bytes + bytes(data)
                    try:
                        self.udp_sock.sendto(packet, (self.relay_host, self.relay_port))
                    except Exception:
                        pass
        except Exception:
            pass

    # ----------------- UDP Receiver Loop -----------------

    def _recv_loop(self):
        """Receives incoming video and audio packets from peer via UDP relay."""
        audio_stream = None
        if SOUNDDEVICE_AVAILABLE:
            try:
                audio_stream = sd.RawOutputStream(
                    samplerate=AUDIO_SAMPLE_RATE,
                    blocksize=AUDIO_BLOCK_SIZE,
                    channels=AUDIO_CHANNELS,
                    dtype="int16"
                )
                audio_stream.start()
            except Exception:
                audio_stream = None

        while self.running and self.udp_sock:
            try:
                data, _ = self.udp_sock.recvfrom(65535)
                if len(data) < 2:
                    continue

                tag = data[0]
                target_len = data[1]
                payload = data[2 + target_len:]

                if tag == TAG_VIDEO:
                    self._render_remote_video(payload)
                elif tag == TAG_AUDIO and audio_stream and not self.mic_muted:
                    try:
                        audio_stream.write(payload)
                    except Exception:
                        pass

            except (socket.error, OSError):
                if not self.running:
                    break

        if audio_stream:
            try:
                audio_stream.stop()
                audio_stream.close()
            except Exception:
                pass

    def _render_remote_video(self, frame_data: bytes):
        """Renders received peer video frame in the Call Window."""
        if not self.call_window or not frame_data:
            return

        try:
            photo = tk.PhotoImage(data=frame_data)

            def _apply():
                if self.remote_video_label and self.remote_video_label.winfo_exists():
                    self.remote_video_label.configure(image=photo, text="")
                    self._current_remote_img = photo

            if self.call_window.winfo_exists():
                self.call_window.after(0, _apply)
        except Exception:
            pass

    def end_call(self):
        """Terminates the call and cleans up resources."""
        if not self.running:
            return
        self.running = False

        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
            self.udp_sock = None

        if self.call_window and self.call_window.winfo_exists():
            try:
                self.call_window.destroy()
            except Exception:
                pass

        if self.on_call_ended:
            self.on_call_ended()
