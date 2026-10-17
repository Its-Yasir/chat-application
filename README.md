# Real-Time Multi-User Chat Application

A secure, multi-threaded, real-time chat application built with Python socket programming. Features an obsidian-themed Tkinter GUI, AES-128 end-to-end encryption, group rooms, direct private messaging, file sharing, and UDP media calling simulation.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (tested on Python 3.14)
- (Optional) Install media dependencies for voice & video:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Start the Server
In a terminal window:
```bash
python run_server.py
```
*The server listens for TCP chat connections on port 5555 and UDP media traffic on port 5556.*

### 3. Launch Clients
In one or more separate terminal windows:
```bash
python run_client.py
```
- Enter your nickname (e.g. `Alice`, `Bob`, `Charlie`).
- Connect to `127.0.0.1` (or server LAN IP for multi-device network testing).

### 4. Run Automated Tests
```bash
python test_chat_system.py
```

---

## ✨ Features

- **Multi-Client Concurrency**: Scalable multi-threaded TCP server handling concurrent users with graceful disconnect management.
- **Active User Roster**: Real-time dynamically synchronized sidebar showing online peers.
- **Public & Group Rooms**: Create and join channels (`#General`, `#StudyGroup`), and leave rooms with the "🚪 Leave Room" action.
- **Private Direct Messaging (1-to-1)**: Isolated, private chat tabs between users.
- **Encrypted File Sharing**: Send and receive files, images, and documents securely with automatic download handling.
- **Live Voice & Video Calling**: Real-time low-latency UDP media relay with camera feed (and animated fallback if no camera is available) and microphone/audio playback.
- **End-to-End AES-128 Encryption**: Plaintext never crosses the wire or server memory unencrypted.
- **Modern Obsidian GUI**: Dark, minimal UI built with Python's built-in Tkinter/ttk.

---

For in-depth architectural details, protocol framing, and component breakdown, see [PROJECT_REPORT.md](PROJECT_REPORT.md).
