import socket
import threading

# Настройки для бесплатного облака
HOST = '0.0.0.0'
PORT = 10000 # Стандартный порт для Render

clients = {}

def handle_client(conn, addr):
    try:
        # Получаем ник при входе
        nick = conn.recv(1024).decode('utf-8')
        clients[nick] = conn
        print(f" Пользователь {nick} в сети!")
        
        while True:
            data = conn.recv(1024).decode('utf-8')
            if not data: break
            
            # Рассылка всем
            for c_nick, c_conn in clients.items():
                if c_conn != conn:
                    try:
                        c_conn.send(f"{nick}:{data}".encode('utf-8'))
                    except: pass
    except: pass
    finally:
        conn.close()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen(50)
print(f"Сервер SOIDI запущен на порту {PORT}...")

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle_client, args=(conn, addr)).start()
