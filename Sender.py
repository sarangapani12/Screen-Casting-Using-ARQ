import socket
import cv2
import numpy as np
import time
import struct
import argparse
from collections import deque

class ScreenCastSender:
    def __init__(self, my_ip, my_port, peer_ip, peer_port, window_size=5):
        self.window_size = window_size
        self.my_ip = my_ip
        self.my_port = my_port
        self.peer_ip = peer_ip
        self.peer_port = peer_port
        
        # Socket setup
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((my_ip, my_port))
        self.sock.settimeout(0.1)
        
        # Sliding Window Protocol State
        self.next_seq_num = 0
        self.base = 0
        self.sent_packets = {}
        self.ack_received = {}
        
        # Screen capture settings - REDUCED RESOLUTION
        self.screen_width = 800  # Reduced from 1280
        self.screen_height = 600  # Reduced from 720
        self.compression_quality = 50  # Lower quality for smaller packets
        self.max_packet_size = 60000  # Safe UDP packet size
        
        # Stats
        self.sent_count = 0
        self.retransmit_count = 0
        self.running = True
        
        print(f"🚀 SCREEN CAST SENDER STARTED!")
        print(f"🔢 Window Size: {window_size}")
        print(f"📡 My Address: {my_ip}:{my_port}")
        print(f"👥 Receiver Address: {peer_ip}:{peer_port}")
        print("=" * 50)

    def capture_screen(self):
        """Capture screen using pyscreenshot"""
        try:
            import pyscreenshot as ImageGrab
            # Capture entire screen
            img_pil = ImageGrab.grab()
            img_np = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            img_resized = cv2.resize(img_np, (self.screen_width, self.screen_height))
            return img_resized
        except ImportError:
            # Fallback: create test pattern if pyscreenshot not available
            return self.create_test_pattern()
        except Exception as e:
            print(f"❌ Screen capture error: {e}")
            return self.create_test_pattern()

    def create_test_pattern(self):
        """Create test pattern when screen capture is not available"""
        img = np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)
        
        # Add some moving elements for visual feedback
        t = time.time()
        x = int((t % 10) * self.screen_width / 10)
        y = int((t % 8) * self.screen_height / 8)
        
        cv2.rectangle(img, (x, 100), (x + 200, 200), (0, 255, 0), -1)
        cv2.circle(img, (y + 300, 300), 50, (255, 0, 0), -1)
        cv2.putText(img, 'SCREEN CAST TEST PATTERN', (50, 500), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(img, f'Frame: {self.sent_count}', (50, 550), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return img

    def compress_frame(self, frame, quality=50):
        """Compress frame using JPEG with size check"""
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        result, encoded = cv2.imencode('.jpg', frame, encode_param)
        
        if not result:
            return None
            
        compressed_data = encoded.tobytes()
        
        # If still too large, reduce quality further
        if len(compressed_data) > self.max_packet_size:
            print(f"⚠️ Frame too large ({len(compressed_data)} bytes), reducing quality...")
            return self.compress_frame(frame, quality - 10)
        
        return compressed_data

    def split_large_frame(self, frame_data, max_chunk_size=60000):
        """Split large frames into multiple chunks"""
        if len(frame_data) <= max_chunk_size:
            return [frame_data]
        
        chunks = []
        total_chunks = (len(frame_data) + max_chunk_size - 1) // max_chunk_size
        
        for i in range(total_chunks):
            start = i * max_chunk_size
            end = min((i + 1) * max_chunk_size, len(frame_data))
            chunks.append(frame_data[start:end])
        
        print(f"📦 Split frame into {len(chunks)} chunks")
        return chunks

    def send_frame_with_protocol(self, frame_data):
        """Send frame using sliding window protocol with chunking"""
        if self.next_seq_num - self.base >= self.window_size:
            return False
        
        # Split frame into chunks if too large
        chunks = self.split_large_frame(frame_data)
        
        for chunk_index, chunk_data in enumerate(chunks):
            # Create packet: [4-byte length] + [4-byte seq_num] + [1-byte chunk_index] + [1-byte total_chunks] + [data]
            header = struct.pack('>IIBB', len(chunk_data), self.next_seq_num, chunk_index, len(chunks))
            packet = header + chunk_data
            
            # Check final packet size
            if len(packet) > 65507:
                print(f"❌ Packet still too large: {len(packet)} bytes. Skipping frame.")
                return False
            
            try:
                self.sock.sendto(packet, (self.peer_ip, self.peer_port))
                
            except Exception as e:
                print(f"❌ Send error: {e}")
                return False
        
        # Store for retransmission (store the original frame data)
        self.sent_packets[self.next_seq_num] = {
            'frame_data': frame_data,  # Store original data for retransmission
            'timestamp': time.time(),
            'retries': 0
        }
        self.ack_received[self.next_seq_num] = False
        
        print(f"📤 SENT frame {self.next_seq_num} ({len(chunks)} chunks, {len(frame_data)} bytes)")
        self.next_seq_num += 1
        self.sent_count += 1
        return True

    def retransmit_frame(self, seq_num):
        """Retransmit a specific frame"""
        if seq_num not in self.sent_packets:
            return False
            
        packet_info = self.sent_packets[seq_num]
        frame_data = packet_info['frame_data']
        
        chunks = self.split_large_frame(frame_data)
        
        for chunk_index, chunk_data in enumerate(chunks):
            header = struct.pack('>IIBB', len(chunk_data), seq_num, chunk_index, len(chunks))
            packet = header + chunk_data
            
            try:
                self.sock.sendto(packet, (self.peer_ip, self.peer_port))
            except Exception as e:
                print(f"❌ Retransmit send error: {e}")
                return False
        
        packet_info['timestamp'] = time.time()
        packet_info['retries'] += 1
        self.retransmit_count += 1
        print(f"🔄 RETRANSMITTED frame {seq_num} (attempt {packet_info['retries']})")
        return True

    def process_acks(self):
        """Process incoming ACK packets"""
        try:
            while True:
                data, addr = self.sock.recvfrom(65536)
                
                if len(data) == 4:
                    # This is an ACK packet
                    ack_seq = struct.unpack('>I', data)[0]
                    if ack_seq in self.ack_received and not self.ack_received[ack_seq]:
                        self.ack_received[ack_seq] = True
                        
                        # Remove from sent packets
                        if ack_seq in self.sent_packets:
                            del self.sent_packets[ack_seq]
                        
                        # Slide window forward
                        while self.base in self.ack_received and self.ack_received[self.base]:
                            del self.ack_received[self.base]
                            self.base += 1
                        
                        print(f"✅ ACK for frame {ack_seq}, window: [{self.base}-{self.next_seq_num-1}]")
                        
        except socket.timeout:
            pass
        except Exception as e:
            print(f"❌ ACK processing error: {e}")

    def check_timeouts(self):
        """Check for timed out packets and retransmit"""
        current_time = time.time()
        timeout = 1.0  # 1 second timeout
        
        for seq_num, packet_info in list(self.sent_packets.items()):
            if (current_time - packet_info['timestamp'] > timeout and 
                packet_info['retries'] < 3 and 
                not self.ack_received.get(seq_num, False)):
                
                self.retransmit_frame(seq_num)

    def get_protocol_visualization(self):
        """Create protocol visualization window"""
        width, height = 600, 400
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Title
        cv2.putText(img, 'SENDER - SLIDING WINDOW PROTOCOL', (width//8, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Draw window visualization
        window_start = max(0, self.base - 2)
        window_end = self.base + self.window_size + 2
        
        for i in range(window_start, window_end + 1):
            x = 50 + (i - window_start) * 40
            y = height // 2
            
            # Determine status
            if i < self.base:
                color = (0, 255, 0)  # ACKed (Green)
                status = "ACKed"
            elif i == self.next_seq_num:
                color = (255, 255, 0)  # Next to send (Yellow)
                status = "Next"
            elif i < self.next_seq_num:
                if self.ack_received.get(i, False):
                    color = (0, 255, 0)  # ACKed (Green)
                    status = "ACKed"
                else:
                    color = (255, 165, 0)  # Sent, waiting ACK (Orange)
                    status = f"Sent"
            elif i < self.base + self.window_size:
                color = (100, 100, 255)  # Available (Blue)
                status = "Ready"
            else:
                color = (50, 50, 50)  # Outside window (Dark)
                status = "Future"
            
            # Draw packet box
            cv2.rectangle(img, (x-15, y-15), (x+15, y+15), color, -1)
            cv2.rectangle(img, (x-15, y-15), (x+15, y+15), (255, 255, 255), 2)
            cv2.putText(img, str(i), (x-8, y+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)
        
        # Window boundaries
        window_left = 50 + (self.base - window_start) * 40 - 20
        window_right = 50 + (self.base + self.window_size - window_start) * 40 - 20
        cv2.rectangle(img, (window_left, 80), (window_right, 180), (255, 255, 255), 2)
        
        # Statistics
        stats_y = 250
        cv2.putText(img, f'Base: {self.base}, Next: {self.next_seq_num}', (50, stats_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Window Size: {self.window_size}', (50, stats_y + 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Total Sent: {self.sent_count}', (50, stats_y + 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Retransmissions: {self.retransmit_count}', (50, stats_y + 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Unacked: {len(self.sent_packets)}', (50, stats_y + 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Legend
        legends = [
            ("ACKed", (0, 255, 0)),
            ("Sent, Waiting ACK", (255, 165, 0)),
            ("Ready to Send", (100, 100, 255)),
            ("Next to Send", (255, 255, 0))
        ]
        
        for i, (text, color) in enumerate(legends):
            y_pos = height - 30 - i * 25
            cv2.rectangle(img, (width-200, y_pos-8), (width-185, y_pos+7), color, -1)
            cv2.putText(img, text, (width-180, y_pos+5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
        
        return img

    def run(self):
        """Main loop"""
        frame_count = 0
        last_stats_time = 0
        last_send_time = 0
        
        print("🎬 Starting screen casting with sliding window protocol...")
        print("💡 Press 'Q' to quit\n")
        
        # Set Qt platform to xcb for Linux
        import os
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
        
        try:
            while self.running:
                current_time = time.time()
                
                # CAPTURE AND SEND SCREEN (every 100ms)
                if current_time - last_send_time > 0.1:
                    screen_frame = self.capture_screen()
                    
                    # Compress frame
                    compressed = self.compress_frame(screen_frame, self.compression_quality)
                    if compressed:
                        # Send using sliding window protocol
                        if self.send_frame_with_protocol(compressed):
                            frame_count += 1
                            last_send_time = current_time
                
                # PROCESS ACKS
                self.process_acks()
                
                # CHECK TIMEOUTS AND RETRANSMIT
                self.check_timeouts()
                
                # DISPLAY SCREEN CAST WINDOW
                display_screen = screen_frame.copy() if 'screen_frame' in locals() else self.create_test_pattern()
                cv2.putText(display_screen, f'Screen Cast - Frame {frame_count}', (20, 40), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(display_screen, f'Total Sent: {self.sent_count}', (20, 80), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(display_screen, f'Retransmissions: {self.retransmit_count}', (20, 110), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow('1 - Screen Cast (Sender) - Press Q to quit', display_screen)
                
                # DISPLAY PROTOCOL VISUALIZATION
                protocol_viz = self.get_protocol_visualization()
                cv2.imshow('2 - Sender Sliding Window Protocol', protocol_viz)
                
                # PRINT STATISTICS every 3 seconds
                if current_time - last_stats_time > 3.0:
                    print(f"📊 STATS: Sent: {self.sent_count}, Retrans: {self.retransmit_count}, Unacked: {len(self.sent_packets)}")
                    last_stats_time = current_time
                
                # CHECK FOR EXIT
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.running = False
                
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down sender...")
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
        
        # Cleanup
        cv2.destroyAllWindows()
        self.sock.close()
        print("\n✅ Screen cast sender ended")
        print(f"📊 Final: {self.sent_count} frames sent, {self.retransmit_count} retransmissions")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Screen Cast Sender with Sliding Window Protocol')
    parser.add_argument('--my-ip', required=True, help='Your PC IP address')
    parser.add_argument('--my-port', type=int, default=10000, help='Your port')
    parser.add_argument('--peer-ip', required=True, help='Receiver PC IP address')
    parser.add_argument('--peer-port', type=int, default=10001, help='Receiver port')
    parser.add_argument('--window-size', type=int, default=5, help='Sliding window size')
    
    args = parser.parse_args()
    
    # Install pyscreenshot if not available
    try:
        import pyscreenshot
    except ImportError:
        print("⚠️  pyscreenshot not installed. Installing...")
        import subprocess
        subprocess.check_call(["pip", "install", "pyscreenshot"])
        import pyscreenshot
    
    sender = ScreenCastSender(
        args.my_ip,
        args.my_port,
        args.peer_ip,
        args.peer_port,
        window_size=args.window_size
    )
    sender.run()
