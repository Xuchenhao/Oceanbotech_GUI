import sys
from PyQt5.QtWidgets import QApplication, QWidget, QTableWidgetItem
from PyQt5 import QtCore
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import cv2
import queue
import socket
import re
import json
import time
import numpy as np

Debug_flag = True
Debug_video = False
ONLINE_MODE = False
command_queue = queue.Queue()
ROV_CAMERA_IP_ADDR = "rtsp://192.168.10.10:554/user=admin&password=&channel=1&stream=0.sdp?"
OFFLINE_DATA = b'{"sensors":{"depth_adc":14.55,"depth":0.15,"battery":10,"status":0,"battery_adc":52071,"roll":-0.31,"yaw":174.96,"pitch":2.56,"water_temp":21.22,"cabin_temp":37.53,"humidity":42.34,"observer_mode":0,"drive_loop":0,"light_state":0},"debug":{"m1":0,"set_depth":0.00,"set_speed":0.00}}\r\n{"sensors":{"depth_adc":15.10,"depth":0.15,"battery":10,"status":0,"battery_adc":52056,"roll":-0.31,"yaw":173.47,"pitch":2.56,"water_temp":21.22,"cabin_temp":37.53,"humidity":42.34,"observer_mode":0,"drive_loop":0,"light_state":0},"debug":{"m1":0,"set_depth":0.00,"set_speed":0.00}}'


def to_json(str):
    return json.dumps(str)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        if ONLINE_MODE:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建一个socket
            self.sock.connect(('192.168.10.200', 8899))  # 建立连接
        else: self.sock = 0
        self.cmd_thread = AnalyzeCommand(self.sock)
        self.update_thread = UpdateData(self.sock)
        self.video_thread = VideoData(self.sock)
        self.cam_show_flag = True
        self.initUI()

    def initUI(self):
        # self.setGeometry(300, 300, 300, 200)
        # self.setFixedWidth(200)
        # self.setFixedHeight(200)
        self.setWindowTitle('OceanBotech ROV')
        self.setWindowIcon(QIcon("oceanbotech.png"))

        main_layout = QtWidgets.QHBoxLayout()
        fun_button = QtWidgets.QVBoxLayout()
        self.data_table = self.get_data_table()

        # camera_layout = QtWidgets.QVBoxLayout()

        self.label_show_camera = QtWidgets.QLabel()
        self.label_show_camera.setFixedSize(641, 481)
        self.label_show_camera.setAutoFillBackground(False)

        self.button_open_camera = QtWidgets.QPushButton(u'Open Camera')
        self.button_open_camera.setFixedSize(120, 50)
        fun_button.addWidget(self.button_open_camera)
        self.button_open_camera.clicked.connect(self.open_camera_on_click)

        button_close = QtWidgets.QPushButton(u'Quit')
        button_close.setFixedSize(120, 50)
        fun_button.addWidget(button_close)
        button_close.clicked.connect(self.close)

        fun_button.addWidget(self.data_table)

        main_layout.addLayout(fun_button)
        main_layout.addWidget(self.label_show_camera)
        self.setLayout(main_layout)
        self.update_thread.update_date.connect(self.update_item_data)
        self.video_thread.frame_data.connect(self.show_img)

        self.show()
        self.cmd_thread.start()
        self.update_thread.start()

    def get_data_table(self):
        data_table = QtWidgets.QTableWidget()
        data_table.setMaximumSize(300, 400)
        data_table.setColumnCount(1)
        data_table.setRowCount(6)
        col_name = [
            'Data',

        ]
        data_table.setHorizontalHeaderLabels(col_name)
        row_name = [
            'Depth', #深度
            'Battery', #电池
            'Humidity', #湿度
            'cabin_temp', #机体温度
            'yaw',
            'pitch',
        ]
        data_table.setVerticalHeaderLabels(row_name)
        return data_table

    def update_item_data(self, x,y,z,a,b,c):
        self.data_table.setItem(0, 0, QTableWidgetItem(x))
        self.data_table.setItem(1, 0, QTableWidgetItem(y))
        self.data_table.setItem(2, 0, QTableWidgetItem(z))
        self.data_table.setItem(3, 0, QTableWidgetItem(a))
        self.data_table.setItem(4, 0, QTableWidgetItem(b))
        self.data_table.setItem(5, 0, QTableWidgetItem(c))

    def keyPressEvent(self, event):
        key = event.key()
        if Debug_flag: print("pressed:" + str(key))
        if key == Qt.Key_Escape:
            self.close()
        elif key == Qt.Key_W:
            command_queue.put('command_type:1')  # forward
        elif key == Qt.Key_S:
            command_queue.put('command_type:2')  # backward
        elif key == Qt.Key_A:
            command_queue.put('command_type:3')  # left
        elif key == Qt.Key_D:
            command_queue.put('command_type:4')  # right
        elif key == Qt.Key_R:
            command_queue.put('command_type:5')  # loop
        elif key == Qt.Key_Q:
            command_queue.put('command_type:6')  # light
        elif key == Qt.Key_Z:
            command_queue.put('command_type:7')  # up
        elif key == Qt.Key_X:
            command_queue.put('command_type:8')  # down

    def open_camera_on_click(self):
        if Debug_video: print('LCH: opencv_camera initiated.')
        if self.cam_show_flag:
            self.video_thread.start()
            self.video_thread.cam_timer.start(30)
            self.button_open_camera.setText(u'Close Camera')
            self.cam_show_flag = False
        else:
            if Debug_video: print('LCH: open_camera_on_click: 5')
            self.video_thread.cam_timer.stop()
            self.cam_show_flag = True
            # self.video_thread.quit()
            # self.video_thread.wait()
            self.label_show_camera.clear()
            self.button_open_camera.setText(u'Open Camera')

    def show_img(self, frame):
        if Debug_video: print('LCH: Main thread show img.')
        showImage = QtGui.QImage(frame.data, frame.shape[1], frame.shape[0], QtGui.QImage.Format_RGB888)
        self.label_show_camera.setPixmap(QtGui.QPixmap.fromImage(showImage))


class VideoData(QThread):
    frame_data = pyqtSignal(np.ndarray)

    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self.cam_num = ROV_CAMERA_IP_ADDR if ONLINE_MODE else 0
        self.cap = cv2.VideoCapture(self.cam_num)
        self.frame = np.zeros([480, 640])

        self.cam_timer = QtCore.QTimer()
        self.cam_timer.timeout.connect(self.push_img)

    def run(self):
        if Debug_video: print('LCH: Video thread begin...')
        while True:
            ret, img = self.cap.read()
            if ret:
                img = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (640, 480))
                if Debug_video: print('LCH: img processed...')
                # self.frame = cv2.resize(cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB), (640, 480))
                self.frame = img.copy()
            time.sleep(0.01)

    def push_img(self):
        if Debug_video: print('LCH: push_img begin...')
        self.frame_data.emit(self.frame)
        if Debug_video: print('LCH: push_img done.')


class AnalyzeCommand(QThread):
    def __init__(self, sock):
        super().__init__()
        self.led_count = 1
        self.loop_count = 1
        self.sock = sock

    def run(self):
        cmd_message = 'command_type:0'
        if Debug_flag: print('LCH: the AnalyzeCommand Initialized!')
        run_flag = False
        stop_ret = True
        while 1:
            while not command_queue.empty():
                cmd_message = command_queue.get()
                run_flag = True
                stop_ret = True
            if not stop_ret: continue
            if run_flag:
                # print("LCH: the cmd_message is", cmd_message)
                send_message, stop_ret = self.analyze_json(message=cmd_message)
                run_flag = False
                cmd_message = 'command_type:0'
            else:
                send_message, stop_ret = self.analyze_json(message=cmd_message)
            if Debug_flag: print("LCH: the send_message is: ", send_message)
            if ONLINE_MODE: self.sock.send(send_message.encode('utf-8'))
            time.sleep(0.05)

    def analyze_json(self, message):
        speed = 500
        ret = True
        if message:
            pattern = re.compile(r'\d+')
            command_type = int(re.findall(pattern, message)[0])
            if command_type == 0:
                cmd_string = {"motors": {"set_motor1_speed": 0, "set_motor2_speed": 0, "set_motor3_speed": 0,
                                         "set_motor4_speed": 0}}
                ret = False
            if command_type == 1:
                cmd_string = {"motors": {"set_motor1_speed": speed, "set_motor2_speed": speed, "set_motor3_speed": 0,
                                   "set_motor4_speed": 0}}

            elif command_type == 2:
                cmd_string = {"motors": {"set_motor1_speed": -speed, "set_motor2_speed": -speed, "set_motor3_speed": 0,
                                   "set_motor4_speed": 0}}

            elif command_type == 3:
                cmd_string = {"motors": {"set_motor1_speed": -speed, "set_motor2_speed": speed, "set_motor3_speed": 0,
                                   "set_motor4_speed": 0}}

            elif command_type == 4:
                cmd_string = {"motors": {"set_motor1_speed": speed, "set_motor2_speed": -speed, "set_motor3_speed": 0,
                                   "set_motor4_speed": 0}}

            elif command_type == 5:
                loop = self.loop_count % 2
                cmd_string = {"buttons": {"drive_loop": loop}}
                self.loop_count += 1

            elif command_type == 6:
                led = self.led_count % 2
                cmd_string = {"leds": {"led_control": led}}
                self.led_count += 1

            elif command_type == 7:
                cmd_string = {"motors": {"set_motor1_speed": 0, "set_motor2_speed": 0, "set_motor3_speed": speed,
                                   "set_motor4_speed": speed}}

            elif command_type == 8:
                cmd_string = {"motors": {"set_motor1_speed": 0, "set_motor2_speed": 0, "set_motor3_speed": -speed,
                                   "set_motor4_speed": -speed}}

        send_message = to_json(cmd_string)

        return send_message, ret


class UpdateData(QThread):
    update_date = pyqtSignal(str,str,str,str,str,str)

    def __init__(self, sock):
        super().__init__()
        self.sock = sock

    def run(self):
        if Debug_flag: print('LCH: UpdateData QThread start!')
        while True:
            if ONLINE_MODE:
                recv_data = self.sock.recv(1024)
            else:
                recv_data = OFFLINE_DATA
            if recv_data:
                if Debug_flag: print('LCH: Recv Data:', recv_data)
                recv_message = recv_data.decode('utf-8')
                if Debug_flag: print('LCH: Recv Message:', recv_message)
                pattern = re.compile(r'\{"sensors".*\}\}')
                recv_message_slice = re.findall(pattern, recv_message)[-1]
                if Debug_flag: print('LCH: Recv Message Slice:', recv_message_slice)
                if recv_message_slice:
                    stringData = json.loads(recv_message_slice)
                    if Debug_flag: print('LCH: StringData:', stringData)
                    cnt = stringData['sensors']['depth_adc']
                    cnt1 = stringData['sensors']['battery']
                    cnt2 = stringData['sensors']['humidity']
                    cnt3 = stringData['sensors']['cabin_temp']
                    cnt4 = stringData['sensors']['yaw']
                    cnt5 = stringData['sensors']['pitch']

                    if Debug_flag: print('LCH: Updating...')
                    self.update_date.emit(str(cnt),str(cnt1),str(cnt2),str(cnt3),str(cnt4),str(cnt5))
                    if Debug_flag: print('LCH: Update done')
                    time.sleep(0.05)
                else:
                    time.sleep(0.5)
                    continue


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window()
    sys.exit(app.exec_())