import sys
import socket
import threading
import sqlite3
import cv2
import os
import pyaudio
import numpy as np
import random
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout,
                             QHBoxLayout, QWidget, QLabel, QTextEdit, QLineEdit,
                             QListWidget, QStackedWidget, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QImage, QPixmap, QPainter, QBrush, QColor, QPainterPath

# ==========================================================
# КОНФИГУРАЦИЯ И АВТООБНОВЛЕНИЕ
# ==========================================================
CURRENT_VERSION = 1.0 

# ЗАМЕНИ 'nikitishe2014-ship-it' на свой ник GitHub, если он другой!
VERSION_URL = "https://raw.githubusercontent.com"
UPDATE_URL = "https://raw.githubusercontent.com"

SERVER_HOST = 'gondola.proxy.rlwy.net'
SERVER_PORT = 32766

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

BAD_ROOTS = ["хуй", "хуе", "хуи", "пизд", "еба", "ебл", "ебт", "бля", "сук", "мудак", "гандон", "чмо"]

def apply_filter(text):
    if not text: return ""
    words = text.split()
    clean = []
    for w in words:
        check = "".join(filter(str.isalpha, w.lower()))
        is_bad = any(root in check for root in BAD_ROOTS)
        clean.append("[ЦЕНЗУРА]" if is_bad else w)
    return " ".join(clean)

class SoidiSignals(QObject):
    msg_received = pyqtSignal(str, str)
    img_received = pyqtSignal(str, QPixmap)
    call_incoming = pyqtSignal(str)
    friend_req_incoming = pyqtSignal(str)
    system_log = pyqtSignal(str)

class SoidiUltimateMessenger(QMainWindow):
    def __init__(self):
        super().__init__()

        self.check_for_updates()

        self.db = sqlite3.connect('soidi_data.db', check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS users (nick TEXT, pwd TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS friends (nick TEXT)")
        self.db.commit()

        self.signals = SoidiSignals()
        self.signals.msg_received.connect(self.on_msg_received)
        self.signals.img_received.connect(self.on_img_received)
        self.signals.call_incoming.connect(self.on_call_incoming)
        self.signals.friend_req_incoming.connect(self.on_friend_req_incoming)
        self.signals.system_log.connect(self.add_system_msg)

        self.my_nick = None
        self.client_socket = None
        self.target_user = "ALL"
        self.is_calling = False
        self.cap = None

        try:
            self.audio_sys = pyaudio.PyAudio()
            self.stream_out = self.audio_sys.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
        except: pass

        self.setWindowTitle(f"SOIDI Messenger v{CURRENT_VERSION}")
        self.resize(1100, 800)
        self.setStyleSheet("background-color: #0B0D14; color: white;")

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.circle_timer = QTimer()
        self.circle_timer.timeout.connect(self.update_video_circle)

        self.build_ui()
        QTimer.singleShot(500, self.check_account_status)

    def check_for_updates(self):
        try:
            response = requests.get(VERSION_URL, timeout=5)
            if response.status_code == 200:
                remote_version = float(response.text.strip())
                if remote_version > CURRENT_VERSION:
                    self.perform_update()
        except: pass

    def perform_update(self):
        try:
            new_code = requests.get(UPDATE_URL).content
            current_script = os.path.abspath(sys.argv[0])
            with open(current_script, 'wb') as f:
                f.write(new_code)
            os.execl(sys.executable, sys.executable, *sys.argv)
        except: pass

    def build_ui(self):
        self.auth_page = QWidget(); al = QVBoxLayout(self.auth_page)
        logo = QLabel("SOIDI"); logo.setFont(QFont("Impact", 100)); logo.setStyleSheet("color: #00FFCC;"); logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reg_nick = QLineEdit(); self.reg_nick.setPlaceholderText("Никнейм")
        self.reg_pwd = QLineEdit(); self.reg_pwd.setPlaceholderText("Пароль"); self.reg_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        btn = QPushButton("СОЗДАТЬ АККАУНТ"); btn.clicked.connect(self.process_registration)
        for w in [logo, self.reg_nick, self.reg_pwd, btn]:
            w.setFixedSize(400, 60 if w != logo else 150)
            al.addWidget(w, alignment=Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.auth_page)

        self.main_page = QWidget(); ml = QHBoxLayout(self.main_page)
        left = QVBoxLayout()
        self.prof_label = QLabel("👤 Профиль"); self.prof_label.setStyleSheet("color: #00FFCC; font-weight: bold;")
        btn_copy = QPushButton("📋 КОПИРОВАТЬ ID"); btn_copy.clicked.connect(self.copy_my_id)
        self.friend_in = QLineEdit(); self.friend_in.setPlaceholderText("Ник#1234")
        btn_add = QPushButton("ДОБАВИТЬ"); btn_add.clicked.connect(self.send_friend_request)
        self.contact_list = QListWidget(); self.contact_list.addItem("🌍 ОБЩИЙ ЧАТ"); self.contact_list.itemClicked.connect(self.on_contact_click)
        self.btn_call = QPushButton("📞 ПОЗВОНИТЬ"); self.btn_call.clicked.connect(self.toggle_voice_call); self.btn_call.setStyleSheet("background: #2ECC71; color: white; height: 50px;")
        for w in [self.prof_label, btn_copy, self.friend_in, btn_add, self.contact_list, self.btn_call]: left.addWidget(w)
        
        right = QVBoxLayout()
        self.chat_display = QTextEdit(); self.chat_display.setReadOnly(True); self.chat_display.setStyleSheet("background: #08090E; border-radius: 15px;")
        self.video_view = QLabel(); self.video_view.setFixedSize(160, 160); self.video_view.hide()
        bar = QHBoxLayout()
        self.msg_input = QLineEdit(); self.msg_input.returnPressed.connect(self.send_message)
        btn_cam = QPushButton("⭕"); btn_cam.clicked.connect(self.toggle_cam); btn_cam.setFixedSize(45, 45)
        btn_send = QPushButton("➡"); btn_send.clicked.connect(self.send_message); btn_send.setFixedSize(50, 45); btn_send.setStyleSheet("background: #00FFCC;")
        bar.addWidget(btn_cam); bar.addWidget(self.msg_input); bar.addWidget(btn_send)
        right.addWidget(self.chat_display); right.addWidget(self.video_view, alignment=Qt.AlignmentFlag.AlignCenter); right.addLayout(bar)
        ml.addLayout(left, 1); ml.addLayout(right, 3)
        self.stack.addWidget(self.main_page)

    def network_worker(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((SERVER_HOST, SERVER_PORT))
            self.client_socket.send(f"AUTH:{self.my_nick}".encode('utf-8'))
            self.signals.system_log.emit(f"В сети! Твой ID: {self.my_nick}")
            while True:
                data = self.client_socket.recv(1024 * 1024)
                if not data: break
                if data.startswith(b"VOX:"):
                    if self.is_calling: self.stream_out.write(data[4:])
                else:
                    try:
                        m = data.decode('utf-8')
                        if m.startswith("REQ:"): self.signals.friend_req_incoming.emit(m.split(":", 1)[1])
                        elif m.startswith("CALL:"): self.signals.call_incoming.emit(m.split(":", 1)[1])
                        elif ":" in m:
                            s, t = m.split(":", 1); self.signals.msg_received.emit(s, t)
                    except: pass
        except: self.signals.system_log.emit("Ошибка связи")

    def process_registration(self):
        n, p = self.reg_nick.text().strip(), self.reg_pwd.text().strip()
        if n and p:
            self.my_nick = f"{n}#{random.randint(1000, 9999)}"
            self.db.execute("DELETE FROM users"); self.db.execute("INSERT INTO users VALUES (?,?)", (self.my_nick, p)); self.db.commit()
            self.launch_messenger()

    def launch_messenger(self):
        self.prof_label.setText(f"👤 {self.my_nick}\n🟢 ONLINE")
        self.stack.setCurrentIndex(1)
        self.contact_list.clear(); self.contact_list.addItem("🌍 ОБЩИЙ ЧАТ")
        for row in self.db.execute("SELECT nick FROM friends").fetchall(): self.contact_list.addItem(row[0])
        threading.Thread(target=self.network_worker, daemon=True).start()

    def check_account_status(self):
        res = self.db.execute("SELECT nick FROM users LIMIT 1").fetchone()
        if res: self.my_nick = res[0]; self.launch_messenger()
        else: self.stack.setCurrentIndex(0)

    def send_message(self):
        txt = self.msg_input.text().strip()
        if txt and self.client_socket:
            safe = apply_filter(txt)
            self.client_socket.send(f"{self.target_user}:{safe}".encode('utf-8'))
            self.chat_display.append(f"<b style='color:#00FFCC;'>Вы:</b> {safe}"); self.msg_input.clear()

    def on_msg_received(self, s, t): self.chat_display.append(f"<b style='color:#FF4747;'>{s}:</b> {t}")
    def copy_my_id(self): QApplication.clipboard().setText(self.my_nick); self.add_system_msg("ID скопирован!")
    def send_friend_request(self):
        t = self.friend_in.text().strip()
        if t and self.client_socket: self.client_socket.send(f"REQ:{t}".encode('utf-8')); self.add_system_msg("Заявка отправлена")

    def on_friend_req_incoming(self, s):
        if QMessageBox.question(self, "Заявка", f"Добавить {s}?") == QMessageBox.StandardButton.Yes:
            self.client_socket.send(f"ACC:{s}".encode('utf-8'))
            if not self.db.execute("SELECT nick FROM friends WHERE nick=?", (s,)).fetchone():
                self.db.execute("INSERT INTO friends VALUES (?)", (s,)); self.db.commit(); self.contact_list.addItem(s)

    def toggle_voice_call(self):
        if self.target_user == "ALL": return
        self.is_calling = not self.is_calling
        self.btn_call.setText("🛑 КОНЕЦ" if self.is_calling else "📞 ПОЗВОНИТЬ")
        if self.is_calling:
            self.client_socket.send(f"CALL:{self.target_user}".encode('utf-8'))
            threading.Thread(target=self.voice_sender, daemon=True).start()

    def voice_sender(self):
        p = pyaudio.PyAudio(); s = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        while self.is_calling:
            try: self.client_socket.sendall(b"VOX:" + s.read(CHUNK, False))
            except: break
        s.stop_stream(); s.close(); p.terminate()

    def toggle_cam(self):
        if not self.cap: self.cap = cv2.VideoCapture(0); self.video_view.show(); self.circle_timer.start(30)
        else: self.circle_timer.stop(); self.cap.release(); self.cap = None; self.video_view.hide()

    def update_video_circle(self):
        if self.cap:
            ret, f = self.cap.read()
            if ret:
                f = cv2.resize(f, (160, 160)); f = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
                img = QImage(f.data, 160, 160, 160*3, QImage.Format.Format_RGB888)
                pix = QPixmap(160, 160); pix.fill(Qt.GlobalColor.transparent)
                p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setBrush(QBrush(img)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(0,0,160,160); p.end()
                self.video_view.setPixmap(pix)

    def on_img_received(self, s, p): pass
    def on_call_incoming(self, c): self.add_system_msg(f"📞 Тебе звонит {c}!")
    def add_system_msg(self, t): self.chat_display.append(f"<i style='color:#555;'>[SOIDI]: {t}</i>")
    def on_contact_click(self, i): self.target_user = i.text(); self.add_system_msg(f"Выбран чат: {self.target_user}")

if __name__ == "__main__":
    app = QApplication(sys.argv); win = SoidiUltimateMessenger(); win.show(); sys.exit(app.exec())
