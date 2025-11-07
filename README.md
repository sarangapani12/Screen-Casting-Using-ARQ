# Screen-Casting-Using-ARQ
This project implements ARQ protocols (Selective Repeat) to achieve reliable screen casting over unstable networks. It simulates packet loss and delay, analyzing retransmissions, throughput, and latency to ensure smooth and efficient real-time video streaming.
# 🎥 Reliable Screen Casting using ARQ Protocols

This project demonstrates **reliable video/screen streaming** using **Automatic Repeat reQuest (ARQ)** technique Selective Repeat.  
It simulates data delivery over an **unreliable network channel** with configurable packet loss and delay, showcasing how ARQ mechanisms improve streaming performance and user experience.

---

## 🚀 Project Overview

**Theme:** Reliable Video Streaming over Unstable Networks  
**Objective:** To ensure reliable and real-time screen casting using ARQ error control mechanisms.  
**Core Concepts:** Flow control, Error control, Sliding window protocols.

### ✳️ Features
- Real-time screen capture and transmission over UDP sockets  
- Simulation of packet loss, delay, and reordering  
- Implementation ARQ protocol:
   - Selective Repeat
- Logging and performance analysis (throughput, retransmissions, latency)
- Comparative analysis of ARQ protocols under various network conditions

---

## 🛠️ Tools and Technologies
- **Language:** Python 3  
- **Libraries:** `socket`, `mss`, `opencv-python`, `numpy`, `asyncio`, `matplotlib`, `pandas`  
- **Optional:** `aiortc` (for WebRTC integration), `ffmpeg` (for compression)  
- **Simulation tools:** Custom Unreliable Channel / Mininet / MATLAB (optional)

---

## ⚙️ How It Works

1. **Sender:** Captures the screen using `mss` or `opencv` → Encodes frame → Packetizes and sends via UDP.  
2. **Channel:** Introduces controlled loss, delay, and duplication.  
3. **Receiver:** Receives packets → Acknowledges (ACK/NACK) based on ARQ protocol → Reassembles and displays frames.  
4. **Metrics:** Calculates throughput, retransmissions, and frame delivery rate.

---

## 📊 Evaluation Metrics
- Retransmission count  
- Throughput (effective bits/sec)  
- Average delay and jitter  
- Delivered FPS (frames per second)  
- PSNR/SSIM (video quality measurement)

---


