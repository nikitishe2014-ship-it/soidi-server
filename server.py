import socket
import threading

# Настройки для облака (Railway/Render)
HOST = '0.0.0.0'
PORT = 10000 

# База активных соединений {Никнейм: Объект_Сокета}
clients = {}

def handle_client(conn, addr):
    """Функция обработки каждого отдельного пользователя"""
    my_nick = None
    print(f"[СЕРВЕР] Новое подключение: {addr}")
    
    try:
        # 1. Приветственный протокол: получаем Никнейм
        my_nick = conn.recv(1024).decode('utf-8').strip()
        if not my_nick:
            conn.close()
            return
            
        clients[my_nick] = conn
        print(f"[СЕРВЕР] Пользователь '{my_nick}' теперь в сети. Всего: {len(clients)}")
        
        # Уведомляем всех о входе (кроме вошедшего)
        broadcast_msg = f"SYSTEM:{my_nick} присоединился к сети!"
        for name, sock in clients.items():
            if name != my_nick:
                try: sock.send(broadcast_msg.encode('utf-8'))
                except: pass

        # 2. Основной цикл прослушивания сообщений
        while True:
            data = conn.recv(4096).decode('utf-8')
            if not data:
                break
            
            # Протокол сообщений: "ПОЛУЧАТЕЛЬ:ТЕКСТ"
            if ":" in data:
                target, message = data.split(":", 1)
                
                # Если пишут всем (Общий чат)
                if target == "ALL":
                    final_msg = f"{my_nick}:{message}"
                    for name, sock in clients.items():
                        if name != my_nick: # Себе не шлем (клиент сам отрисует)
                            try: sock.send(final_msg.encode('utf-8'))
                            except: pass
                
                # Если пишут конкретному человеку (Личка)
                elif target in clients:
                    final_msg = f"{my_nick}:{message}"
                    try: clients[target].send(final_msg.encode('utf-8'))
                    except: pass
                
                # Если адресат не найден
                else:
                    conn.send(f"SYSTEM:Пользователь {target} не найден или вышел.".encode('utf-8'))

    except Exception as e:
        print(f"[СЕРВЕР] Ошибка с пользователем {my_nick}: {e}")
    
    finally:
        # Убираем пользователя из списка при выходе
        if my_nick in clients:
            del clients[my_nick]
            # Уведомляем остальных
            exit_msg = f"SYSTEM:{my_nick} покинул чат."
            for name, sock in clients.items():
                try: sock.send(exit_msg.encode('utf-8'))
                except: pass
        
        conn.close()
        print(f"[СЕРВЕР] Соединение с {addr} закрыто.")

# Запуск сервера
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    server.bind((HOST, PORT))
    server.listen(100) # Максимум 100 человек
    print(f"========================================")
    print(f" СЕРВЕР SOIDI ЗАПУЩЕН НА ПОРТУ {PORT}")
    print(f"========================================")
except Exception as e:
    print(f"[ОШИБКА] Не удалось запустить сервер: {e}")

while True:
    conn, addr = server.accept()
    thread = threading.Thread(target=handle_client, args=(conn, addr))
    thread.daemon = True
    thread.start()
