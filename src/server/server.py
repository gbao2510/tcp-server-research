import socket
import json
import struct
import logging
from concurrent.futures import ThreadPoolExecutor

# Cấu hình log để dễ theo dõi trên Terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(message)s')

HOST = '127.0.0.1'
PORT = 9999
MAX_WORKERS = 100 

def recvall(sock, n):
    """Hàm đảm bảo đọc đủ số byte từ kết nối"""
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data

def handle_client(conn, addr):
    """Xử lý từng Client độc lập"""
    logging.info(f"[+] Client kết nối: {addr}")
    conn.settimeout(10.0) 
    
    try:
        while True:
            # Bóc tách độ dài gói tin
            raw_msglen = recvall(conn, 4)
            if not raw_msglen:
                break
            
            msglen = struct.unpack('>I', raw_msglen)[0]
            if msglen > 2 * 1024 * 1024: # Chặn payload quá lớn
                break

            # Đọc payload
            data = recvall(conn, msglen)
            if not data:
                break
            
            # Phản hồi
            try:
                request = json.loads(data.decode('utf-8'))
                response = {
                    "requestId": request.get("requestId"),
                    "payload": request.get("payload"),
                    "status": "success"
                }
                
                res_data = json.dumps(response).encode('utf-8')
                res_msg = struct.pack('>I', len(res_data)) + res_data
                conn.sendall(res_msg)

            except json.JSONDecodeError:
                break 
                
    except socket.timeout:
        logging.warning(f"[-] Bị timeout ở kết nối {addr}")
    except Exception:
        pass
    finally:
        conn.close()
        logging.info(f"[-] Đóng kết nối {addr}")

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind((HOST, PORT))
    server_socket.listen(100) 
    
    logging.info(f"[*] Server đang chạy tại {HOST}:{PORT}")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        try:
            while True:
                conn, addr = server_socket.accept()
                executor.submit(handle_client, conn, addr)
        except KeyboardInterrupt:
            logging.info("\n[*] Đang tắt Server...")
        finally:
            server_socket.close()

if __name__ == "__main__":
    start_server()