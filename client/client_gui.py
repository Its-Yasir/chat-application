"""
client_gui.py - Modern & Minimal Graphical User Interface for PyChat.

Design Philosophy:
- Minimalist Obsidian Theme: Deep graphite tones (#111218, #181A24, #222533)
- Modern Typography & Hierarchy: Clean sans-serif with subtle status pills
- End-to-End Encryption Indicators: Visible AES-128 security badges
- Group Management: Dynamic room creation and one-click "🚪 Leave Group" button
- Multi-client & Concurrency: Thread-safe UI updates via root.after()
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import base64
from datetime import datetime
from typing import Dict, List, Optional, Any

# Ensure modules are discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from client.client_core import ClientCore
from client.media_streamer import MediaStreamer
from common.crypto import CRYPTO_AVAILABLE

# Directory where received files will be saved
RECEIVE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "received_files"))
os.makedirs(RECEIVE_DIR, exist_ok=True)

# ----------------- Modern Minimal Color Palette -----------------
BG_DEEP = "#0F1117"          # Darkest background (main window)
BG_SURFACE = "#171923"       # Sidebar & header panels
BG_CARD = "#1F2232"          # Input bar & cards
BG_ACTIVE = "#2B2F45"        # Selected items / hover states
BORDER_SUBTLE = "#2A2E42"    # Divider lines & borders
TEXT_PRIMARY = "#FFFFFF"     # Crisp white
TEXT_SECONDARY = "#949CB5"   # Muted slate
TEXT_MUTED = "#5E657D"       # Dark muted timestamps/labels
ACCENT_PRIMARY = "#6366F1"   # Modern Indigo / Blurple
ACCENT_SUCCESS = "#10B981"   # Emerald Green
ACCENT_DANGER = "#EF4444"    # Soft Coral / Red for Leave & Hangup


class ChatGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PyChat • Minimal & Secure")
        self.root.geometry("1000x680")
        self.root.minsize(820, 540)
        self.root.configure(bg=BG_DEEP)

        # Network client core
        self.client = ClientCore()

        # State tracking
        self.current_username = ""
        self.current_mode = "room"          # "room" or "private"
        self.current_target = "General"      # Room name or username

        # Room member tracker: room_name -> list of usernames
        self.active_rooms: Dict[str, List[str]] = {}
        self.active_users: List[str] = []

        # Conversation histories: "room:General" or "private:Bob" -> list of message items
        self.histories: Dict[str, List[dict]] = {}

        # Media call session
        self.active_streamer: Optional[MediaStreamer] = None

        # Bind network callbacks
        self._register_client_callbacks()

        # Build UI layout
        self._setup_styles()
        self._build_main_layout()

        # Clean shutdown
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Launch modern connection dialog
        self.root.after(100, self._show_connect_dialog)

    def _setup_styles(self):
        """Configures ttk styles for clean modern widgets."""
        style = ttk.Style()
        style.theme_use("clam")

        # Scrollbar
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background=BG_CARD,
            darkcolor=BG_SURFACE,
            lightcolor=BG_CARD,
            troughcolor=BG_DEEP,
            bordercolor=BG_DEEP
        )

        # Entry
        style.configure(
            "TEntry",
            fieldbackground=BG_CARD,
            foreground=TEXT_PRIMARY,
            insertcolor=TEXT_PRIMARY,
            bordercolor=BORDER_SUBTLE
        )

    def _register_client_callbacks(self):
        """Attaches client_core events to thread-safe GUI dispatchers."""
        self.client.on_registered = lambda u: self.root.after(0, self._on_registered_event, u)
        self.client.on_user_list = lambda users: self.root.after(0, self._update_user_list_ui, users)
        self.client.on_room_list = lambda rooms: self.root.after(0, self._update_room_list_ui, rooms)
        self.client.on_message = lambda m, t, s, c, ts: self.root.after(0, self._on_message_event, m, t, s, c, ts)
        self.client.on_file_received = lambda pkt: self.root.after(0, self._on_file_event, pkt)
        self.client.on_call_signal = lambda s, a, ct: self.root.after(0, self._on_call_signal_event, s, a, ct)
        self.client.on_system_message = lambda msg: self.root.after(0, self._on_system_msg_event, msg)
        self.client.on_disconnected = lambda: self.root.after(0, self._on_disconnected_event)

    # ----------------- UI Layout Construction -----------------

    def _build_main_layout(self):
        """Creates the split view: Sleek Sidebar (left) and Clean Chat Area (right)."""
        self.main_container = tk.Frame(self.root, bg=BG_DEEP)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # ================= LEFT SIDEBAR =================
        sidebar = tk.Frame(self.main_container, bg=BG_SURFACE, width=270, bd=0)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
        sidebar.pack_propagate(False)

        # Brand & Profile Container
        brand_frame = tk.Frame(sidebar, bg=BG_SURFACE, height=65)
        brand_frame.pack(fill=tk.X, padx=18, pady=(16, 12))

        app_title = tk.Label(
            brand_frame,
            text="● PyChat",
            font=("Segoe UI", 13, "bold"),
            bg=BG_SURFACE,
            fg=ACCENT_PRIMARY
        )
        app_title.pack(anchor="w")

        self.user_badge = tk.Label(
            brand_frame,
            text="Connecting...",
            font=("Segoe UI", 9),
            bg=BG_SURFACE,
            fg=TEXT_SECONDARY
        )
        self.user_badge.pack(anchor="w", pady=(2, 0))

        # Thin divider
        tk.Frame(sidebar, bg=BORDER_SUBTLE, height=1).pack(fill=tk.X, padx=18, pady=(0, 10))

        # --- CHAT ROOMS (CHANNELS) ---
        rooms_header = tk.Frame(sidebar, bg=BG_SURFACE)
        rooms_header.pack(fill=tk.X, padx=18, pady=(6, 4))

        tk.Label(
            rooms_header,
            text="CHANNELS",
            font=("Segoe UI", 8, "bold"),
            bg=BG_SURFACE,
            fg=TEXT_MUTED
        ).pack(side=tk.LEFT)

        add_room_btn = tk.Button(
            rooms_header,
            text="+ New",
            font=("Segoe UI", 8, "bold"),
            bg=BG_SURFACE,
            fg=ACCENT_PRIMARY,
            activebackground=BG_ACTIVE,
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=self._prompt_create_room
        )
        add_room_btn.pack(side=tk.RIGHT)

        self.rooms_listbox = tk.Listbox(
            sidebar,
            bg=BG_SURFACE,
            fg=TEXT_SECONDARY,
            selectbackground=BG_ACTIVE,
            selectforeground=TEXT_PRIMARY,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=0,
            activestyle="none",
            height=6
        )
        self.rooms_listbox.pack(fill=tk.X, padx=14, pady=2)
        self.rooms_listbox.bind("<<ListboxSelect>>", self._on_room_selected)

        # Thin divider
        tk.Frame(sidebar, bg=BORDER_SUBTLE, height=1).pack(fill=tk.X, padx=18, pady=(12, 10))

        # --- ONLINE USERS (DIRECT MESSAGES) ---
        users_header = tk.Frame(sidebar, bg=BG_SURFACE)
        users_header.pack(fill=tk.X, padx=18, pady=(4, 4))

        tk.Label(
            users_header,
            text="DIRECT MESSAGES",
            font=("Segoe UI", 8, "bold"),
            bg=BG_SURFACE,
            fg=TEXT_MUTED
        ).pack(side=tk.LEFT)

        self.users_listbox = tk.Listbox(
            sidebar,
            bg=BG_SURFACE,
            fg=TEXT_SECONDARY,
            selectbackground=BG_ACTIVE,
            selectforeground=TEXT_PRIMARY,
            font=("Segoe UI", 10),
            bd=0,
            highlightthickness=0,
            activestyle="none"
        )
        self.users_listbox.pack(fill=tk.BOTH, expand=True, padx=14, pady=2)
        self.users_listbox.bind("<<ListboxSelect>>", self._on_user_selected)

        # Sidebar Footer: Encryption status indicator
        footer_frame = tk.Frame(sidebar, bg=BG_SURFACE, height=35)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=18, pady=12)

        enc_label_text = "🔒 AES-128 E2EE Active" if CRYPTO_AVAILABLE else "🔒 Standard Encryption"
        tk.Label(
            footer_frame,
            text=enc_label_text,
            font=("Segoe UI", 8),
            bg=BG_SURFACE,
            fg=ACCENT_SUCCESS
        ).pack(side=tk.LEFT)

        # ================= RIGHT CHAT PANE =================
        chat_pane = tk.Frame(self.main_container, bg=BG_DEEP)
        chat_pane.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Top Navigation & Header Bar
        self.header_frame = tk.Frame(chat_pane, bg=BG_SURFACE, height=64)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)
        self.header_frame.pack_propagate(False)

        header_left = tk.Frame(self.header_frame, bg=BG_SURFACE)
        header_left.pack(side=tk.LEFT, padx=22, pady=12)

        self.conv_title_label = tk.Label(
            header_left,
            text="# General",
            font=("Segoe UI", 12, "bold"),
            bg=BG_SURFACE,
            fg=TEXT_PRIMARY
        )
        self.conv_title_label.pack(anchor="w")

        self.conv_subtitle_label = tk.Label(
            header_left,
            text="🔒 Encrypted • Group Room",
            font=("Segoe UI", 8),
            bg=BG_SURFACE,
            fg=TEXT_SECONDARY
        )
        self.conv_subtitle_label.pack(anchor="w")

        # Action Buttons on Right side of Header
        self.header_actions = tk.Frame(self.header_frame, bg=BG_SURFACE)
        self.header_actions.pack(side=tk.RIGHT, padx=18, pady=14)

        # "Leave Group" Button (visible when viewing a room)
        self.leave_room_btn = tk.Button(
            self.header_actions,
            text="🚪 Leave Room",
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=ACCENT_DANGER,
            activebackground=BG_ACTIVE,
            activeforeground=ACCENT_DANGER,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._leave_current_room
        )
        self.leave_room_btn.pack(side=tk.RIGHT, padx=4)

        # Call Buttons (visible in 1-to-1 chats)
        self.video_call_btn = tk.Button(
            self.header_actions,
            text="📹 Video Call",
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_PRIMARY,
            fg=TEXT_PRIMARY,
            activebackground="#4F46E5",
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=12,
            pady=4,
            command=self._initiate_video_call
        )

        self.voice_call_btn = tk.Button(
            self.header_actions,
            text="📞 Voice Call",
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            activebackground=BG_ACTIVE,
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._initiate_voice_call
        )

        # Message Feed Container
        feed_container = tk.Frame(chat_pane, bg=BG_DEEP)
        feed_container.pack(fill=tk.BOTH, expand=True, padx=22, pady=(12, 6))

        self.feed_text = tk.Text(
            feed_container,
            bg=BG_DEEP,
            fg=TEXT_PRIMARY,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
            spacing1=3,
            spacing3=4
        )
        feed_scroll = ttk.Scrollbar(feed_container, orient="vertical", command=self.feed_text.yview)
        self.feed_text.configure(yscrollcommand=feed_scroll.set)

        feed_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.feed_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Configure Typography Tags
        self.feed_text.tag_config("time", foreground=TEXT_MUTED, font=("Segoe UI", 8))
        self.feed_text.tag_config("sender_me", foreground=ACCENT_PRIMARY, font=("Segoe UI", 10, "bold"))
        self.feed_text.tag_config("sender_other", foreground="#F59E0B", font=("Segoe UI", 10, "bold"))
        self.feed_text.tag_config("sender_system", foreground=TEXT_MUTED, font=("Segoe UI", 9, "italic"))
        self.feed_text.tag_config("body_me", foreground=TEXT_PRIMARY)
        self.feed_text.tag_config("body_other", foreground="#E2E8F0")
        self.feed_text.tag_config("file_tag", foreground="#38BDF8", font=("Segoe UI", 9, "bold underline"))
        self.feed_text.tag_config("enc_tag", foreground=ACCENT_SUCCESS, font=("Segoe UI", 7))

        # Bottom Floating Pill Input Bar
        input_wrapper = tk.Frame(chat_pane, bg=BG_DEEP)
        input_wrapper.pack(fill=tk.X, side=tk.BOTTOM, padx=22, pady=(4, 18))

        input_pill = tk.Frame(input_wrapper, bg=BG_CARD, bd=1, relief=tk.SOLID)
        input_pill.configure(highlightbackground=BORDER_SUBTLE, highlightthickness=1)
        input_pill.pack(fill=tk.X)

        # Attachment Button
        attach_btn = tk.Button(
            input_pill,
            text="📎",
            font=("Segoe UI", 12),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            activebackground=BG_ACTIVE,
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._on_attach_file
        )
        attach_btn.pack(side=tk.LEFT, padx=(6, 2))

        # Text Entry Field
        self.msg_entry = tk.Entry(
            input_pill,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI", 10)
        )
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=8, ipady=4)
        self.msg_entry.bind("<Return>", lambda e: self._send_chat_message())

        # Send Button
        send_btn = tk.Button(
            input_pill,
            text="Send ➤",
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_PRIMARY,
            fg=TEXT_PRIMARY,
            activebackground="#4F46E5",
            activeforeground=TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._send_chat_message
        )
        send_btn.pack(side=tk.RIGHT, padx=6, pady=6)

    # ----------------- Connection Modal -----------------

    def _show_connect_dialog(self):
        """Displays modern minimalist modal for connecting to the server."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Join PyChat")
        dialog.geometry("360x320")
        dialog.resizable(False, False)
        dialog.configure(bg=BG_SURFACE)
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 180
        y = (dialog.winfo_screenheight() // 2) - 160
        dialog.geometry(f"+{x}+{y}")

        title = tk.Label(
            dialog,
            text="● Welcome to PyChat",
            font=("Segoe UI", 13, "bold"),
            bg=BG_SURFACE,
            fg=ACCENT_PRIMARY
        )
        title.pack(pady=(24, 4))

        subtitle = tk.Label(
            dialog,
            text="End-to-End Encrypted Socket Messaging",
            font=("Segoe UI", 8),
            bg=BG_SURFACE,
            fg=TEXT_MUTED
        )
        subtitle.pack(pady=(0, 16))

        form_frame = tk.Frame(dialog, bg=BG_SURFACE)
        form_frame.pack(fill=tk.X, padx=30)

        # Server Host
        tk.Label(form_frame, text="Server Host / IP", font=("Segoe UI", 8, "bold"),
                 bg=BG_SURFACE, fg=TEXT_SECONDARY).pack(anchor="w", pady=(4, 2))
        host_entry = tk.Entry(form_frame, bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
                              relief=tk.FLAT, font=("Segoe UI", 10), bd=0)
        host_entry.insert(0, "127.0.0.1")
        host_entry.pack(fill=tk.X, ipady=4, pady=(0, 6))

        # Username
        tk.Label(form_frame, text="Your Username", font=("Segoe UI", 8, "bold"),
                 bg=BG_SURFACE, fg=TEXT_SECONDARY).pack(anchor="w", pady=(4, 2))
        user_entry = tk.Entry(form_frame, bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
                              relief=tk.FLAT, font=("Segoe UI", 10), bd=0)
        user_entry.insert(0, f"User_{os.getpid() % 1000}")
        user_entry.pack(fill=tk.X, ipady=4, pady=(0, 4))
        user_entry.focus()

        err_label = tk.Label(dialog, text="", font=("Segoe UI", 8), bg=BG_SURFACE, fg=ACCENT_DANGER)
        err_label.pack(pady=2)

        def _do_connect():
            host = host_entry.get().strip() or "127.0.0.1"
            username = user_entry.get().strip()
            if not username:
                err_label.config(text="Username cannot be empty!")
                return

            self.client.host = host
            self.client.port = 5555
            success = self.client.connect(username)

            if success:
                dialog.destroy()
            else:
                err_label.config(text=f"Could not connect to {host}:5555.\nIs run_server.py running?")

        connect_btn = tk.Button(
            dialog,
            text="Connect & Start",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT_PRIMARY,
            fg=TEXT_PRIMARY,
            activebackground="#4F46E5",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=16,
            pady=7,
            command=_do_connect
        )
        connect_btn.pack(fill=tk.X, padx=30, pady=(10, 15))

    # ----------------- GUI Events & State -----------------

    def _on_registered_event(self, assigned_username: str):
        """Called when server acknowledges registration."""
        self.current_username = assigned_username
        self.user_badge.config(
            text=f"● {assigned_username} (Online)",
            fg=ACCENT_SUCCESS
        )
        self._switch_conversation("room", "General")

    def _update_user_list_ui(self, users: List[str]):
        """Refreshes the online users sidebar."""
        self.active_users = users
        self.users_listbox.delete(0, tk.END)
        for u in users:
            display = f"● {u} (You)" if u == self.current_username else f"● {u}"
            self.users_listbox.insert(tk.END, display)

    def _update_room_list_ui(self, rooms: Dict[str, List[str]]):
        """Refreshes the rooms sidebar."""
        self.active_rooms = rooms
        self.rooms_listbox.delete(0, tk.END)
        for r_name, members in rooms.items():
            count = len(members)
            prefix = "✓ " if r_name == self.current_target and self.current_mode == "room" else "# "
            self.rooms_listbox.insert(tk.END, f"{prefix}{r_name} ({count})")

        # Update member count in header if in a room
        if self.current_mode == "room" and self.current_target in self.active_rooms:
            member_count = len(self.active_rooms[self.current_target])
            self.conv_subtitle_label.config(text=f"🔒 Encrypted • {member_count} member(s)")

    def _on_message_event(self, mode: str, target: str, sender: str, content: str, timestamp: str):
        """Handles incoming decrypted chat message."""
        if mode == "room":
            key = f"room:{target}"
        else:
            peer = target if sender == self.current_username else sender
            key = f"private:{peer}"

        msg_item = {
            "type": "text",
            "sender": sender,
            "content": content,
            "time": timestamp
        }
        self.histories.setdefault(key, []).append(msg_item)

        current_key = f"{self.current_mode}:{self.current_target}"
        if key == current_key:
            self._render_message_bubble(msg_item)

    def _on_file_event(self, packet: dict):
        """Handles incoming decrypted file transfer."""
        mode = packet.get("mode", "room")
        target = packet.get("target", "General")
        sender = packet.get("sender", "")
        filename = packet.get("filename", "received_file")
        filesize = packet.get("filesize", 0)
        timestamp = packet.get("timestamp", "")
        b64_data = packet.get("data", "")

        saved_path = os.path.join(RECEIVE_DIR, filename)
        if sender != self.current_username and b64_data:
            try:
                file_bytes = base64.b64decode(b64_data)
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(saved_path):
                    saved_path = os.path.join(RECEIVE_DIR, f"{base}_{counter}{ext}")
                    counter += 1

                with open(saved_path, "wb") as f:
                    f.write(file_bytes)
            except Exception as e:
                print(f"Error saving file: {e}")

        if mode == "room":
            key = f"room:{target}"
        else:
            peer = target if sender == self.current_username else sender
            key = f"private:{peer}"

        file_item = {
            "type": "file",
            "sender": sender,
            "filename": filename,
            "filesize": filesize,
            "filepath": saved_path,
            "time": timestamp
        }
        self.histories.setdefault(key, []).append(file_item)

        current_key = f"{self.current_mode}:{self.current_target}"
        if key == current_key:
            self._render_file_bubble(file_item)

    def _on_system_msg_event(self, msg: str):
        now_str = datetime.now().strftime("%H:%M")
        sys_item = {"type": "system", "content": msg, "time": now_str}
        current_key = f"{self.current_mode}:{self.current_target}"
        self.histories.setdefault(current_key, []).append(sys_item)
        self._render_system_bubble(sys_item)

    def _on_disconnected_event(self):
        self.user_badge.config(text="● Disconnected", fg=ACCENT_DANGER)
        messagebox.showwarning("Connection Lost", "Disconnected from chat server.")

    # ----------------- Navigation & Conversation Switching -----------------

    def _switch_conversation(self, mode: str, target: str):
        """Switches conversation between room and direct message."""
        self.current_mode = mode
        self.current_target = target

        if mode == "room":
            self.conv_title_label.config(text=f"# {target}")
            members = self.active_rooms.get(target, [])
            count = len(members) if members else 1
            self.conv_subtitle_label.config(text=f"🔒 Encrypted • {count} member(s)")

            # Show Leave Room button
            self.leave_room_btn.pack(side=tk.RIGHT, padx=4)
            self.video_call_btn.pack_forget()
            self.voice_call_btn.pack_forget()
        else:
            self.conv_title_label.config(text=f"@{target}")
            self.conv_subtitle_label.config(text="🔒 End-to-End Encrypted • Direct Message")

            # Show Call buttons, hide Leave Room button
            self.leave_room_btn.pack_forget()
            self.video_call_btn.pack(side=tk.RIGHT, padx=4)
            self.voice_call_btn.pack(side=tk.RIGHT, padx=4)

        # Clear feed and render conversation history
        self.feed_text.configure(state=tk.NORMAL)
        self.feed_text.delete("1.0", tk.END)

        key = f"{mode}:{target}"
        for item in self.histories.get(key, []):
            if item["type"] == "text":
                self._render_message_bubble(item)
            elif item["type"] == "file":
                self._render_file_bubble(item)
            elif item["type"] == "system":
                self._render_system_bubble(item)

        self.feed_text.configure(state=tk.DISABLED)
        self.feed_text.see(tk.END)

    def _leave_current_room(self):
        """Exits the currently active group room."""
        if self.current_mode != "room":
            return

        room_to_leave = self.current_target
        ans = messagebox.askyesno(
            "Exit Room",
            f"Are you sure you want to exit #{room_to_leave}?"
        )
        if not ans:
            return

        # Notify server to remove client from this room
        self.client.send_room_action("leave", room_to_leave)

        # Switch to General or remaining room
        if room_to_leave != "General":
            self._switch_conversation("room", "General")
        else:
            self._switch_conversation("room", "General")

    def _on_room_selected(self, event):
        sel = self.rooms_listbox.curselection()
        if not sel:
            return
        raw_text = self.rooms_listbox.get(sel[0])
        # Format: "# General (2)" or "✓ General (2)"
        room_name = raw_text.split(" (")[0].replace("# ", "").replace("✓ ", "").strip()
        self.client.send_room_action("join", room_name)
        self._switch_conversation("room", room_name)

    def _on_user_selected(self, event):
        sel = self.users_listbox.curselection()
        if not sel:
            return
        raw_text = self.users_listbox.get(sel[0])
        target_user = raw_text.replace("● ", "").replace(" (You)", "").strip()
        if target_user == self.current_username:
            return
        self._switch_conversation("private", target_user)

    # ----------------- Message Rendering -----------------

    def _render_message_bubble(self, item: dict):
        self.feed_text.configure(state=tk.NORMAL)
        sender = item["sender"]
        is_me = (sender == self.current_username)
        time_str = f" {item['time']}  "

        self.feed_text.insert(tk.END, time_str, "time")
        if is_me:
            self.feed_text.insert(tk.END, "You  ", "sender_me")
            self.feed_text.insert(tk.END, "🔒\n", "enc_tag")
            self.feed_text.insert(tk.END, f"{item['content']}\n\n", "body_me")
        else:
            self.feed_text.insert(tk.END, f"{sender}  ", "sender_other")
            self.feed_text.insert(tk.END, "🔒\n", "enc_tag")
            self.feed_text.insert(tk.END, f"{item['content']}\n\n", "body_other")

        self.feed_text.configure(state=tk.DISABLED)
        self.feed_text.see(tk.END)

    def _render_file_bubble(self, item: dict):
        self.feed_text.configure(state=tk.NORMAL)
        sender = item["sender"]
        is_me = (sender == self.current_username)
        filename = item["filename"]
        size_kb = item["filesize"] / 1024.0
        time_str = f" {item['time']}  "

        self.feed_text.insert(tk.END, time_str, "time")
        sender_lbl = "You" if is_me else sender
        sender_tag = "sender_me" if is_me else "sender_other"
        self.feed_text.insert(tk.END, f"{sender_lbl} shared an encrypted file:\n", sender_tag)

        # File Card
        self.feed_text.insert(tk.END, f"   📎 {filename} ({size_kb:.1f} KB) 🔒\n", "file_tag")
        filepath = item.get("filepath", "")
        if filepath and os.path.exists(filepath):
            self.feed_text.insert(tk.END, f"   Saved to: {filepath}\n\n", "time")
        else:
            self.feed_text.insert(tk.END, "\n")

        self.feed_text.configure(state=tk.DISABLED)
        self.feed_text.see(tk.END)

    def _render_system_bubble(self, item: dict):
        self.feed_text.configure(state=tk.NORMAL)
        self.feed_text.insert(tk.END, f"● {item['content']}  [{item['time']}]\n\n", "sender_system")
        self.feed_text.configure(state=tk.DISABLED)
        self.feed_text.see(tk.END)

    # ----------------- Actions -----------------

    def _send_chat_message(self):
        content = self.msg_entry.get().strip()
        if not content:
            return
        self.msg_entry.delete(0, tk.END)
        self.client.send_message(self.current_mode, self.current_target, content)

    def _on_attach_file(self):
        filepath = filedialog.askopenfilename(
            title="Choose File to Encrypt & Send",
            filetypes=[
                ("All Supported Files", "*.*"),
                ("Images", "*.png;*.jpg;*.jpeg;*.gif"),
                ("Videos", "*.mp4;*.avi;*.mov;*.mkv"),
                ("Documents", "*.pdf;*.txt;*.docx;*.zip")
            ]
        )
        if not filepath:
            return
        self.client.send_file(self.current_mode, self.current_target, filepath)

    def _prompt_create_room(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Create Channel")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.configure(bg=BG_SURFACE)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Channel Name", font=("Segoe UI", 9, "bold"),
                 bg=BG_SURFACE, fg=TEXT_SECONDARY).pack(pady=(18, 4))

        room_entry = tk.Entry(dialog, bg=BG_CARD, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
                              font=("Segoe UI", 10), relief=tk.FLAT, bd=0)
        room_entry.pack(fill=tk.X, padx=25, ipady=4, pady=4)
        room_entry.focus()

        def _create():
            name = room_entry.get().strip().replace(" ", "-")
            if name:
                self.client.send_room_action("create", name)
                self._switch_conversation("room", name)
                dialog.destroy()

        btn = tk.Button(dialog, text="Create", font=("Segoe UI", 9, "bold"),
                        bg=ACCENT_PRIMARY, fg=TEXT_PRIMARY, relief=tk.FLAT, bd=0,
                        cursor="hand2", padx=14, pady=5, command=_create)
        btn.pack(pady=12)

    # ----------------- Calling -----------------

    def _initiate_video_call(self):
        if self.current_mode != "private":
            return
        target = self.current_target
        self.client.send_call_signal("request", target, call_type="video_audio")
        self._on_system_msg_event(f"Calling @{target}...")

    def _initiate_voice_call(self):
        if self.current_mode != "private":
            return
        target = self.current_target
        self.client.send_call_signal("request", target, call_type="voice_only")
        self._on_system_msg_event(f"Voice calling @{target}...")

    def _on_call_signal_event(self, sender: str, action: str, call_type: str):
        if action == "request":
            call_label = "Video Call" if call_type == "video_audio" else "Voice Call"
            ans = messagebox.askyesno(
                "Incoming Call",
                f"📞 {sender} is calling you with a {call_label}!\n\nDo you want to accept?"
            )
            if ans:
                self.client.send_call_signal("accept", sender, call_type=call_type)
                self._start_media_stream(sender)
            else:
                self.client.send_call_signal("decline", sender, call_type=call_type)

        elif action == "accept":
            self._on_system_msg_event(f"@{sender} accepted your call.")
            self._start_media_stream(sender)

        elif action == "decline":
            self._on_system_msg_event(f"@{sender} declined the call.")
            messagebox.showinfo("Call Declined", f"{sender} declined the call.")

        elif action == "end":
            self._on_system_msg_event(f"Call with @{sender} ended.")
            if self.active_streamer:
                self.active_streamer.end_call()
                self.active_streamer = None

    def _start_media_stream(self, peer: str):
        if self.active_streamer:
            self.active_streamer.end_call()

        self.active_streamer = MediaStreamer(
            relay_host=self.client.host,
            relay_port=5556,
            my_username=self.current_username,
            peer_username=peer,
            on_call_ended=lambda: self.client.send_call_signal("end", peer)
        )
        self.active_streamer.start_call(self.root)

    def _on_close(self):
        if self.active_streamer:
            self.active_streamer.end_call()
        self.client.disconnect()
        self.root.destroy()


def run_app():
    root = tk.Tk()
    app = ChatGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_app()
