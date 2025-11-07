import socket
import cv2
import numpy as np
import time
import struct
import argparse
from collections import defaultdict

class ScreenCastReceiver:
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
        
        # Receiver state
        self.expected_seq_num = 0
        self.receive_buffer = {}
        self.frame_chunks = defaultdict(dict)  # Store chunks for each frame
        self.frame_total_chunks = {}  # Store total chunks expected for each frame
        
        # Stats
        self.recv_count = 0
        self.duplicate_count = 0
        self.running = True
        
        print(f"🚀 SCREEN CAST RECEIVER STARTED!")
        print(f"🔢 Window Size: {window_size}")
        print(f"📡 My Address: {my_ip}:{my_port}")
        print(f"👥 Sender Address: {peer_ip}:{peer_port}")
        print("=" * 50)

    def decompress_frame(self, data):
        """Decompress JPEG frame"""
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)

    def send_ack(self, seq_num):
        """Send ACK for received packet"""
        try:
            ack_packet = struct.pack('>I', seq_num)
            self.sock.sendto(ack_packet, (self.peer_ip, self.peer_port))
            print(f"✅ ACK for frame {seq_num}")
        except Exception as e:
            print(f"❌ ACK send error: {e}")

    def reassemble_frame(self, seq_num):
        """Reassemble frame from chunks"""
        if seq_num not in self.frame_chunks:
            return None
            
        chunks_dict = self.frame_chunks[seq_num]
        total_chunks = self.frame_total_chunks.get(seq_num, 0)
        
        # Check if we have all chunks
        if len(chunks_dict) != total_chunks:
            return None
        
        # Sort chunks by index and combine
        frame_data = b''
        for i in range(total_chunks):
            if i in chunks_dict:
                frame_data += chunks_dict[i]
            else:
                return None  # Missing chunk
        
        # Clean up
        del self.frame_chunks[seq_num]
        if seq_num in self.frame_total_chunks:
            del self.frame_total_chunks[seq_num]
        
        return frame_data

    def process_incoming_packets(self):
        """Process all incoming packets"""
        try:
            while True:
                data, addr = self.sock.recvfrom(65536)
                
                if len(data) >= 10:  # Minimum header size
                    # This is a data packet with chunk info
                    # Header: [4-byte length] + [4-byte seq_num] + [1-byte chunk_index] + [1-byte total_chunks]
                    header = data[:10]
                    chunk_data = data[10:]
                    
                    try:
                        data_length, seq_num, chunk_index, total_chunks = struct.unpack('>IIBB', header)
                        
                        # Validate packet
                        if len(chunk_data) != data_length:
                            print(f"⚠️ Chunk size mismatch for frame {seq_num}")
                            continue
                        
                        # Store chunk
                        if seq_num not in self.frame_chunks:
                            self.frame_chunks[seq_num] = {}
                        
                        self.frame_chunks[seq_num][chunk_index] = chunk_data
                        self.frame_total_chunks[seq_num] = total_chunks
                        
                        # Try to reassemble frame
                        frame_data = self.reassemble_frame(seq_num)
                        
                        if frame_data is not None:
                            frame = self.decompress_frame(frame_data)
                            
                            if frame is not None:
                                # Send ACK immediately
                                self.send_ack(seq_num)
                                
                                # Handle packet sequencing
                                if seq_num == self.expected_seq_num:
                                    # Expected packet
                                    self.expected_seq_num += 1
                                    self.recv_count += 1
                                    
                                    # Deliver any buffered packets
                                    while self.expected_seq_num in self.receive_buffer:
                                        print(f"📦 Delivering buffered frame {self.expected_seq_num}")
                                        self.expected_seq_num += 1
                                        self.recv_count += 1
                                    
                                    return frame, seq_num, addr
                                elif seq_num > self.expected_seq_num:
                                    # Out-of-order packet - buffer it
                                    print(f"🔄 Out-of-order frame {seq_num}, buffering")
                                    self.receive_buffer[seq_num] = frame
                                    return None, seq_num, addr
                                else:
                                    # Duplicate packet
                                    self.duplicate_count += 1
                                    print(f"🔄 Duplicate frame {seq_num}, ignoring")
                                    return None, seq_num, addr
                        else:
                            # Still waiting for chunks
                            print(f"📦 Received chunk {chunk_index+1}/{total_chunks} for frame {seq_num}")
                            return None, seq_num, addr
                                
                    except struct.error as e:
                        print(f"❌ Packet parsing error: {e}")
                        continue
                                
        except socket.timeout:
            pass
        except Exception as e:
            print(f"❌ Packet processing error: {e}")
        
        return None, None, None

    def get_protocol_visualization(self):
        """Create protocol visualization window"""
        width, height = 600, 400
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Title
        cv2.putText(img, 'RECEIVER - SLIDING WINDOW PROTOCOL', (width//8, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Draw window visualization
        window_start = max(0, self.expected_seq_num - 2)
        window_end = self.expected_seq_num + self.window_size + 2
        
        for i in range(window_start, window_end + 1):
            x = 50 + (i - window_start) * 40
            y = height // 2
            
            # Determine status
            if i < self.expected_seq_num:
                color = (0, 255, 0)  # Delivered (Green)
                status = "Delivered"
            elif i == self.expected_seq_num:
                color = (255, 255, 0)  # Expected next (Yellow)
                status = "Expected"
            elif i in self.receive_buffer:
                color = (255, 165, 0)  # Buffered (Orange)
                status = "Buffered"
            elif i < self.expected_seq_num + self.window_size:
                color = (100, 100, 255)  # Waiting (Blue)
                status = "Waiting"
            else:
                color = (50, 50, 50)  # Future (Dark)
                status = "Future"
            
            # Draw packet box
            cv2.rectangle(img, (x-15, y-15), (x+15, y+15), color, -1)
            cv2.rectangle(img, (x-15, y-15), (x+15, y+15), (255, 255, 255), 2)
            cv2.putText(img, str(i), (x-8, y+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)
        
        # Window boundaries
        window_left = 50 + (self.expected_seq_num - window_start) * 40 - 20
        window_right = 50 + (self.expected_seq_num + self.window_size - window_start) * 40 - 20
        cv2.rectangle(img, (window_left, 80), (window_right, 180), (255, 255, 255), 2)
        
        # Statistics
        stats_y = 250
        cv2.putText(img, f'Expected: {self.expected_seq_num}', (50, stats_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Window Size: {self.window_size}', (50, stats_y + 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Total Received: {self.recv_count}', (50, stats_y + 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Buffered: {len(self.receive_buffer)}', (50, stats_y + 90), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Duplicates: {self.duplicate_count}', (50, stats_y + 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(img, f'Incomplete: {len(self.frame_chunks)}', (50, stats_y + 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Legend
        legends = [
            ("Delivered", (0, 255, 0)),
            ("Expected Next", (255, 255, 0)),
            ("Buffered", (255, 165, 0)),
            ("Waiting", (100, 100, 255))
        ]
        
        for i, (text, color) in enumerate(legends):
            y_pos = height - 30 - i * 25
            cv2.rectangle(img, (width-200, y_pos-8), (width-185, y_pos+7), color, -1)
            cv2.putText(img, text, (width-180, y_pos+5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
        
        return img

    def run(self):
        """Main loop"""
        last_stats_time = 0
        last_frame_time = time.time()
        
        print("🎬 Starting screen cast receiver...")
        print("💡 Press 'Q' to quit\n")
        
        # Set Qt platform to xcb for Linux
        import os
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
        
        try:
            while self.running:
                current_time = time.time()
                
                # PROCESS INCOMING PACKETS
                recv_frame, seq_num, addr = self.process_incoming_packets()
                
                if recv_frame is not None:
                    # DISPLAY RECEIVED SCREEN
                    display_screen = recv_frame.copy()
                    cv2.putText(display_screen, f'Remote Screen - Frame {seq_num}', (20, 40), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
                    cv2.putText(display_screen, f'From: {addr[0]}', (20, 80), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    cv2.putText(display_screen, f'Total Received: {self.recv_count}', (20, 110), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    cv2.putText(display_screen, f'Buffered: {len(self.receive_buffer)}', (20, 140), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    cv2.imshow('1 - Remote Screen Cast - Press Q to quit', display_screen)
                    last_frame_time = current_time
                
                # DISPLAY PROTOCOL VISUALIZATION
                protocol_viz = self.get_protocol_visualization()
                cv2.imshow('2 - Receiver Sliding Window Protocol', protocol_viz)
                
                # PRINT STATISTICS every 3 seconds
                if current_time - last_stats_time > 3.0:
                    print(f"📊 STATS: Received: {self.recv_count}, Buffered: {len(self.receive_buffer)}, Duplicates: {self.duplicate_count}")
                    last_stats_time = current_time
                
                # Auto-shutdown if no frames received for 10 seconds
                if current_time - last_frame_time > 10.0 and self.recv_count > 0:
                    print("⏰ No frames received for 10 seconds. Shutting down...")
                    self.running = False
                
                # CHECK FOR EXIT
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.running = False
                
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down receiver...")
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
        
        # Cleanup
        cv2.destroyAllWindows()
        self.sock.close()
        print("\n✅ Screen cast receiver ended")
        print(f"📊 Final: {self.recv_count} frames received, {self.duplicate_count} duplicates")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Screen Cast Receiver with Sliding Window Protocol')
    parser.add_argument('--my-ip', required=True, help='Your PC IP address')
    parser.add_argument('--my-port', type=int, default=10001, help='Your port')
    parser.add_argument('--peer-ip', required=True, help='Sender PC IP address')
    parser.add_argument('--peer-port', type=int, default=10000, help='Sender port')
    parser.add_argument('--window-size', type=int, default=5, help='Sliding window size')
    
    args = parser.parse_args()
    
    receiver = ScreenCastReceiver(
        args.my_ip,
        args.my_port,
        args.peer_ip,
        args.peer_port,
        window_size=args.window_size
    )
    receiver.run()
