import sys
import sqlite3
import threading
import time
import webbrowser
from datetime import datetime
from plyer import notification

from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QCalendarWidget, QDateTimeEdit,
    QComboBox, QFrame, QTimeEdit, QLineEdit,QTextEdit,QScrollArea,QMessageBox,QLayout,QVBoxLayout,QTextBrowser,
    QGridLayout,QLabel,QStackedWidget,QHBoxLayout,QSpacerItem,QSizePolicy,QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QPropertyAnimation, QEasingCurve, QDate, QDateTime, QTimer
from note_card import NoteCard
from note_card2 import MiniNoteCard
from PySide6.QtCore import Qt,QLocale
from PySide6.QtGui import QIcon
from PySide6.QtCore import QPropertyAnimation,QEasingCurve,QPoint
import winreg
import os
import subprocess
import win10toast_click
from PySide6.QtWidgets import  QAbstractSpinBox
import requests

import inspect
BACKGROUND_FLAG = "--background" in sys.argv
OPEN_MY_FLAG = "--open=my" in sys.argv
APP_NAME = "NoterraApp"



APP_VERSION = "0.9.4"
 

def check_update():
    try:
        url = "https://api.github.com/repos/Raze28K/NoterraV/releases/latest"

        response = requests.get(url, timeout=10)

    except Exception as e:
        print("Ошибка подключения к GitHub:", e)
        return   # ← ВАЖНО! выйти если response нет

    try:
        if response.status_code != 200:
            print("GitHub ответ:", response.status_code, response.text)
            return

        data = response.json()

        if "tag_name" not in data:
            print("Нет релизов")
            return

        latest_version = data["tag_name"].replace("v", "").strip()

        if latest_version != APP_VERSION:
            msg = QMessageBox()
            msg.setWindowTitle("Обновление Noterra")
            msg.setText(f"Доступна новая версия {latest_version}")

            download_btn = msg.addButton("Скачать", QMessageBox.AcceptRole)
            msg.addButton("Позже", QMessageBox.RejectRole)

            msg.exec()

            if msg.clickedButton() == download_btn:
                webbrowser.open(data["html_url"])

    except Exception as e:
        print("Ошибка проверки обновления:", e)


# --- Патч для отладки QMessageBox ---
_original_question = QMessageBox.question

def debug_question(*args, **kwargs):
    print("QMessageBox.question вызван!")
    stack = inspect.stack()
    for s in stack[:5]:
        print(f"{s.function} в {s.filename}:{s.lineno}")
    return _original_question(*args, **kwargs)

QMessageBox.question = debug_question




# уведомления
try:
    from win10toast_click import ToastNotifier
    WIN_TOAST_AVAILABLE = True
except Exception:
    WIN_TOAST_AVAILABLE = False



# Флаг — запущено с параметром открытия вкладки "Мои заметки"
OPEN_MY_FLAG = "--open=my" in sys.argv




def add_to_startup():
    # путь к exe или py
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
    else:
        exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'

    run_value = f'{exe_path} --background'

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_ALL_ACCESS
    )

    try:
        winreg.QueryValueEx(key, APP_NAME)
        print("✔ Уже есть в автозапуске")
    except FileNotFoundError:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, run_value)
        print("✔ Добавлено в автозапуск")

    winreg.CloseKey(key)


# ---------- Удалить из автозапуска ----------
def remove_from_startup():
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_ALL_ACCESS
    )

    try:
        winreg.DeleteValue(key, APP_NAME)
        print("✔ Удалено из автозапуска")
    except FileNotFoundError:
        print("❗ В автозапуске не найдено")

    winreg.CloseKey(key)


# ---------- Проверка ----------
def is_in_startup():
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run"
    )

    try:
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        print("✔ В автозапуске:", value)
    except FileNotFoundError:
        print("❌ Не в автозапуске")

    winreg.CloseKey(key)






DB_NAME = "reminders.db"


# ===== 1. База данных =====
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT,
            remind_at2 TEXT,
            notified INTEGER DEFAULT 0,
            isDone  INTEGER
        )
    """)


    c.execute("""
        CREATE TABLE IF NOT EXISTS trash (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            text TEXT NOT NULL,
            remind_at ,
            remind_at2,
            deleted_at TEXT NOT NULL,
            isDeleted INTEGER,
            isDone  INTEGER
        )
    """)
    conn.commit()
    conn.close()


def add_reminder(title, text, remind_at):
    conn = sqlite3.connect("reminders.db")
    c = conn.cursor()
    c.execute("INSERT INTO reminders (title, text, remind_at) VALUES (?, ?, ?)", (title, text, remind_at))
    conn.commit()
    conn.close()


def reminder_checker():
    """
    Поток проверки напоминаний. При совпадении времени — показываем уведомление.
    Если win10toast_click доступен — делаем кликабельное уведомление, по клику запускаем
    Noterra.exe --open=my (или python main.py --open=my в режиме скрипта).
    """
    notifier = None
    if WIN_TOAST_AVAILABLE:
        notifier = ToastNotifier()

    while True:
        now_dt = datetime.now().replace(second=0, microsecond=0)
        try:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT id, title, text, remind_at, notified FROM reminders WHERE notified = 0")
            rows = c.fetchall()
            for r in rows:
                rem_id, title, text, remind_time, notified = r
                try:
                    remind_dt = datetime.strptime(remind_time, "%d-%m-%Y %H:%M")
                except Exception:
                    # Невалидная дата в БД не должна останавливать весь поток.
                    continue

                # Показываем уведомление и для просроченных задач:
                # так напоминания не теряются после перезапуска приложения.
                if remind_dt <= now_dt:
                    # сначала обновим флаг notified в базе, чтобы не спамить
                    c.execute("UPDATE reminders SET notified = 1 WHERE id = ?", (rem_id,))
                    conn.commit()

                    # Подготовить команду для запуска приложения при клике
                    if getattr(sys, "frozen", False):
                        # если приложение собрано в exe — sys.executable уже указывает на exe
                        target_exe = sys.executable  # путь к Noterra.exe
                        run_cmd = [target_exe, "--open=my"]
                    else:
                        # в режиме скрипта — запускаем python main.py --open=my
                        script_path = os.path.abspath(sys.argv[0])
                        run_cmd = [sys.executable, script_path, "--open=my"]

                    # Показываем уведомление
                    if WIN_TOAST_AVAILABLE:
                        def _on_click():
                            try:
                                subprocess.Popen(run_cmd, close_fds=True)
                            except Exception:
                                try:
                                    os.startfile(run_cmd[0])
                                except Exception:
                                    pass

                        notifier.show_toast(
                            "Noterra",  # <- всегда Noterra
                            text or "",
                            icon_path="icons/Frame1.png",  # можно заменить на путь к .ico если есть
                            duration=10,
                            threaded=True,
                            callback_on_click=_on_click
    )
                    else:
                        pass
        except Exception as e:
            # лог в консоль (чтобы не падало)
            print("reminder_checker error:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        time.sleep(30)


# ===== 2. Главное окно =====
class NoterraApp(QWidget):
    def __init__(self):
        super().__init__()
        self.ISdeleted = None

        self.language = "ru"


        self.translations = {
        "en": {
            "English": "English",
            "New": "Create a new note",
            "My_2":"My notes",
            "Bs":"Trash",
            "label_5":"Events today:",
            "label_13":"There are no events.",
            "label_9":"Settings",
            "label_10":"Change the language",
            "label_11":"Mail",
            "Russian":"Russian",
            "Kazaq":"Kazaq",
            "Corean":"Corean",
            "Em":"Write a letter to the developer",
            "label_6":"Create a new note",
            "label_15":"Note:",
            "label_17":"Name:",
            "Save_note":"Save",
            "label_8":"My notes",
            "CloseNoteViewButton":"Close",
            "label_16":"bascket",
            "close":"Close",
            "delete_all":"delete all",
            "Save_note_frame":"Save",
            "poisk":"Search",
            "poisk_2":"Search"
        
            

            
        },
        "ru":{
            "English": "Английский",
            "New": "Создать новую заметку",
            "My_2":"Мои Заметки",
            "Bs":"Корзина",
            "label_5":"События сегодня:",
            "label_13":"Событий нет.",
            "label_9":"Настройки",
            "label_10":"Сменить язык",
            "label_11":"Письмо",
            "Russian":"Русский",
            "Kazaq":"Казахский",
            "Corean":"Корейский",
            "Em":"Написать письмо разработчику",
            "label_6":"Создать новую заметку",
            "label_15":"Заметка:",
            "label_17":"Имя:",
            "Save_note":"Сохранить",
            "label_8":"Мои заметки",
            "CloseNoteViewButton":"Закрыть",
            "label_16":"Корзина",
            "close":"закрыть",
            "delete_all":"удалить всё",
            "poisk_2":"Поиск",
            "poisk":"Поиск",
            "Save_note_frame":"Сохранить"





        },

        "qaz":{
            "English":"Ағылшын",
            "New":"жаңа жазба жасау",
            "My_2": "Менің Жазбаларым",
            "Bs":"Себет",
            "label_5":"бүгінгі оқиғалар:",
            "label_13": "оқиғалар жоқ.",
            "label_9": "Параметрлер",
            "label_10": "Тілді өзгерту",
            "label_11": "Хат",
            "Russian": "Орыс",
            "Kazaq": "Қазақ",
            "Corean": "Корей",
            "Em":"әзірлеушіге хат жазу",
            "label_6":"жаңа жазба жасау",
            "label_15":"ескерту:",
            "label_17":"аты:",
            "Save_note":"Сақтау",
            "label_8": "менің жазбаларым",
            "CloseNoteViewButton":"Жабу",
            "label_16":"себет",
            "close":"Жабу",
            "delete_all":"барлығын жою",
            "poisk":"Іздеу",
            "poisk_2":"Іздеу",
            "Save_note_frame":"Сақтау"




        },

        "corean":{
            "English":"영어",
            "New":"새 메모 만들기",
            "My_2": "내 노트",
            "Bs":"쓰레기",
            "label_5":"오늘 이벤트:",
            "label_13": "이벤트가 없습니다.",
            "label_9": "설정",
            "label_10": "언어 변경",
            "label_11": "편지",
            "Russian": "러시아어",
            "Kazaq": "카자흐어",
            "Corean": "한국어",
            "Em":"개발자에게 편지 쓰기",
            "label_6":"새 메모 만들기",
            "label_15":"참고:",
            "label_17":"이름:",
            "Save_note":"저장",
            "label_8": "내 노트",
            "CloseNoteViewButton":"닫기",
            "label_16":"쓰레기",
            "close":"닫기",
            "delete_all":"모두 삭제",
            "poisk":"검색",
            "poisk_2":"검색",
            "Save_note_frame":"저장"
            
        }


        
    }

        

        loader = QUiLoader()
        file = QFile("NoterraDark.ui")
        file.open(QFile.ReadOnly)
        self.ui = loader.load(file)
        if not BACKGROUND_FLAG:
            self.ui.show()
        file.close()
        if OPEN_MY_FLAG:
            try:
                # используем тот же стек, что у тебя в коде (у тебя self.stack используется для setCurrentIndex)
                self.stack = self.ui.findChild(QStackedWidget, "stackedWidget")
                self.stack.setCurrentIndex(2) # index 2 — Мои заметки
                # попытаемся поднять окно на передний план
                try:
                    self.ui.activateWindow()
                    self.ui.raise_()
                except Exception:
                    pass
            except Exception as e:
                print("Не удалось переключиться на 'Мои заметки':", e)


        
        
        app.setWindowIcon(QIcon("images/icons/Frame 1.png"))

        

        

        self.status_delete = None
        # ===== Виджеты =====
        self.stack = self.ui.findChild(QWidget, "stackedWidget")
        self.Home = self.ui.findChild(QPushButton, "Home")
        self.Neww = self.ui.findChild(QPushButton, "New")
        self.myy = self.ui.findChild(QPushButton, "My_2")
        self.bac = self.ui.findChild(QPushButton, "Bac")
        self.setng = self.ui.findChild(QPushButton, "Settings_2")
        self.Email = self.ui.findChild(QPushButton, "Em")
        self.backk = self.ui.findChild(QPushButton, "backk")
        self.bss = self.ui.findChild(QPushButton, "Bs")
        self.save_note = self.ui.findChild(QPushButton, "Save_note")
        self.stackedWidget = self.ui.findChild(QStackedWidget,"stackedWidget")

        self.time_combo = self.ui.findChild(QTimeEdit, "timeEdit")
        self.calendar = self.ui.findChild(QCalendarWidget, "calendarWidget")
        self.fr = self.ui.findChild(QFrame, "fr")
        self.date_time_edit = self.ui.findChild(QDateTimeEdit, "dateTimeEdit")
        self.date_time_edit3 = self.ui.findChild(QDateTimeEdit, "dateTimeEdit_3")
        self.date_time_edit3.setDateTime(QDateTime.currentDateTime())
        self.date_time_edit.setDateTime(QDateTime.currentDateTime())
        self.time = self.ui.findChild(QDateTimeEdit, "dateTimeEdit_2")
        self.time2 = self.ui.findChild(QTimeEdit,"timeEdit_2")
        self.month_combo = self.ui.findChild(QComboBox, "monthCombo")
        self.year_combo = self.ui.findChild(QComboBox, "yearCombo")
        self.title_input = self.ui.findChild(QLineEdit, "noteTitle")  # Новый виджет
        self.textEdiit = self.ui.findChild(QTextEdit,"textEdit")
        self.note_scroll = self.ui.findChild(QScrollArea, "noteScrollArea")
        self.note_container = self.ui.findChild(QWidget, "noteContainer")
        self.note_layout = self.note_container.layout()
        
        self.note_layout.setContentsMargins(0, 0, 0, 0)  # убрать лишние отступы
        self.note_layout.setSpacing(10)  
        self.note_view_frame = self.ui.findChild(QFrame, "noteViewFrame")
      
        self.save_note2 = self.ui.findChild(QPushButton,"Save_note_2")
        self.dataTIME2 = self.ui.findChild(QDateTimeEdit,"TI")
        self.dataTIME2.setVisible(False)
        
        self.note_full_text_label = self.ui.findChild(QTextEdit, "noteFullTextLabel")
        self.today_note_full_text_label = self.ui.findChild(QTextEdit,"txtb")
        self.close_note_view_button = self.ui.findChild(QPushButton, "CloseNoteViewButton")
        self.note_name = self.ui.findChild(QLineEdit,"Name_note")
        self.today_note_name = self.ui.findChild(QLineEdit,"today_note_name")
        self.TIMEE = self.ui.findChild(QDateTimeEdit,"TIME")
        self.TIMEE.setVisible(False)
        self.TIMEE.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.TIMEE2=self.ui.findChild(QDateTimeEdit,"TIME2")
        self.Eng = self.ui.findChild(QPushButton,"English")
        self.RU = self.ui.findChild(QPushButton,"Russian")
        self.QAZ = self.ui.findChild(QPushButton,"Kazaq")
        self.corean = self.ui.findChild(QPushButton,"Corean")
        self.light = self.ui.findChild(QPushButton,"Light")
        self.version = self.ui.findChild(QLabel,"label_14")
        self.version.setText(f"Version--{APP_VERSION}")
        
        self.note_view_frame.setVisible(False)
        
        self.note_cards = []
        self.trash_cards = []
        self.load_notes()
        
        
        self.calendar.setVisible(False)
        self.fr.setVisible(False)
        self.trash_scroll = self.ui.findChild(QScrollArea, "trashScrollArea")
        self.trash_container = self.ui.findChild(QWidget, "trash_container")
        self.trash_scroll = self.ui.findChild(QScrollArea, "trashScrollArea")
        self.trash_container = self.ui.findChild(QWidget, "trash_container")
        self.search_input = self.ui.findChild(QLineEdit,"search_input")
        self.Name = self.ui.findChild(QLabel,"Name")
        self.Name.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.Desc = self.ui.findChild(QLabel,"Desc")
        self.Desc.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.delete_all = self.ui.findChild(QPushButton,"delete_all")
        self.timer = QTimer(self)
        self.timer2 = QTimer(self)
        self.scr2 = self.ui.findChild(QScrollArea,"scrollArea_2")

        self.scr2.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.timer2.timeout.connect(self.DELLALL)
        self.timer2.start(2419200)


        self.menu = self.ui.findChild(QPushButton,"Menu")
        self.frameleft = self.ui.findChild(QFrame,"frame_12")
        self.menu2 = self.ui.findChild(QPushButton,"Menu_2")
        self.menu2.setVisible(False)

        self.search_trash = self.ui.findChild(QLineEdit,"seacrh_trash")
        self.frame_note = self.ui.findChild(QFrame,'frame_main')
        self.frame_note.setVisible(False)
        self.save_note_btn = self.ui.findChild(QPushButton,"Save_note_frame")
        self.close_today_note = self.ui.findChild(QPushButton,"close")
        

        self.date_time_edit3.setReadOnly(True)
        self.date_time_edit3.setFocusPolicy(Qt.NoFocus)
        self.line = self.date_time_edit3.lineEdit()
        self.line.setFocusPolicy(Qt.NoFocus)
        self.line.setCursor(Qt.ArrowCursor)
        self.line.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.date_time_edit3.setVisible(False)
        self.time.setFocusPolicy(Qt.NoFocus)
        self.line2 = self.time.lineEdit()
        self.line2.setFocusPolicy(Qt.NoFocus)
        self.line2.setCursor(Qt.ArrowCursor)
        self.line2.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.download = self.ui.findChild(QPushButton,"Download")
        self.save = self.ui.findChild(QPushButton,"save")










        
            


        self.search_input.textChanged.connect(lambda: self.search_notes())
        self.search_trash.textChanged.connect(lambda: self.search_notes2())


        if self.trash_scroll:
    # Получаем тот самый внутренний контейнер из Designer
            self.trash_container = self.trash_scroll.widget()

    # Берём layout или создаём, если его нет
            self.trash_layout = self.trash_container.layout()
            if self.trash_layout is None:
                self.trash_layout = QVBoxLayout(self.trash_container)
                self.trash_container.setLayout(self.trash_layout)

    # Настройки отступов и расстояний
            self.trash_layout.setSpacing(20)
            self.trash_layout.setContentsMargins(20, 20, 20, 20)
        else:
            print("❌ trashScrollArea не найден. Проверь objectName в .ui")




        self.stackedWidget1 = self.ui.findChild(QStackedWidget,"stackedWidget")
        self.event_container = self.ui.findChild(QWidget,"widget_3")
        self.event_scroll = self.ui.findChild(QScrollArea,"scrollArea_2")
        if self.event_container.layout() is None:
            self.event_layout = QVBoxLayout(self.event_container)
            self.event_container.setLayout(self.event_layout)
        else:
            self.event_layout = self.event_container.layout()

        self.event_layout.setSpacing(10)
        self.event_layout.setContentsMargins(10, 10, 10, 10)
        self.event_layout.setAlignment(Qt.AlignTop)

        self.event_scroll.takeWidget()  # убираем то, что было
        self.event_scroll.setWidgetResizable(True)
        self.event_scroll.setWidget(self.event_container)
        self.event_container.setMinimumWidth(300) 


           
        self.month = self.ui.findChild(QComboBox,"month")
        self.year = self.ui.findChild(QComboBox,"year")
        self.calendar2 = self.ui.findChild(QCalendarWidget,"calendarWidget_2")
        self.timeedit = self.ui.findChild(QTimeEdit,"timeEdit_2")
        self.fr2 = self.ui.findChild(QFrame,"fr2")
        self.poisk = self.ui.findChild(QLabel,"poisk")
        self.poisk2 = self.ui.findChild(QLabel,"poisk_2")
        self.save2 = self.ui.findChild(QPushButton,"save_2")

        
        self.calendar2.setVisible(False)
        self.time2.setVisible(False)
        self.month.setVisible(False)
        self.year.setVisible(False)
        self.fr2.setVisible(False)
        
        
                













        self.close_note_view_button.clicked.connect(
            lambda: self.note_view_frame.setVisible(False)
        )
        
        if self.note_container.layout() is None:
            self.note_layout = QGridLayout(self.note_container)
            self.note_container.setLayout(self.note_layout)
        else:
            self.note_layout = self.note_container.layout()

        self.note_layout.setSpacing(20)  # расстояние между карточками
        self.note_layout.setContentsMargins(20, 20, 20, 20)  # отступы от краёв
        self.note_scroll.takeWidget()
        self.note_scroll.setWidgetResizable(True)
        self.note_scroll.setWidget(self.note_container)
        self.note_container.setMinimumWidth(600) 
        self.state = False
        self.load_today_events()

        

        locale = QLocale(QLocale.Russian, QLocale.Russia)



        # ===== Настройки календаря =====
        for m in range(1, 13):
            month_name = locale.monthName(m)  # Возвращает месяц на русском
            self.month_combo.addItem(month_name)
        for y in range(2025, 2100):
            self.year_combo.addItem(str(y))

        for g in range(1,13):
            month_name = locale.monthName(g)  # Возвращает месяц на русском
            self.month.addItem(month_name)

        for i in range(2025, 2100):
            self.year.addItem(str(i))






        today = QDate.currentDate()
        self.month_combo.setCurrentIndex(today.month() - 1)
        self.year_combo.setCurrentText(str(today.year()))

        self.month.setCurrentIndex(today.month() - 1)
        self.year.setCurrentText(str(today.year()))
        self.month.currentIndexChanged.connect(self.update_calendar2)
        self.year.currentIndexChanged.connect(self.update_calendar2)
        self.calendar2.currentPageChanged.connect(self.sync_combos_with_calendar2)
        self.time2.timeChanged.connect(self.update_time_from_timeedit2)
        
        self.calendar2.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)


        



        self.month_combo.currentIndexChanged.connect(self.update_calendar)
        self.year_combo.currentIndexChanged.connect(self.update_calendar)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.currentPageChanged.connect(self.sync_combos_with_calendar)
        self.time_combo.timeChanged.connect(self.update_time_from_timeedit)

        self.calendar.selectionChanged.connect(self.update_date_time_edit)
        # self.calendar2.selectionChanged.connect(self.update_date_time_edit2)



        self.timer = QTimer()
        self.timer.timeout.connect(self.update_current_datetime)
        self.timer.start(1000)
        self.frameleft.setMinimumWidth(0)

    



        
     


        # ===== Сигналы =====
        self.Home.clicked.connect(self.HOMEE)
        
        self.Neww.clicked.connect(self.NEWW)
        self.myy.clicked.connect(self.MYY)
        self.setng.clicked.connect(self.SETT)
        self.bac.clicked.connect(self.BACKKK2)
        self.calendar.clicked.connect(self.BACKKK)
        self.save_note.clicked.connect(self.Save_note)
        self.bss.clicked.connect(self.Bs)
        self.Eng.clicked.connect(self.engg)
        self.RU.clicked.connect(self.ruu)
        self.QAZ.clicked.connect(self.qazz)
        self.corean.clicked.connect(self.cor)
        self.light.clicked.connect(self.lightthema)
        self.delete_all.clicked.connect(self.DELLALL)
        self.menu2.clicked.connect(self.expand_left_bar)
        self.save_note_btn.clicked.connect(self.save_note_changes)
        self.save2.clicked.connect(self.save_note_changes2)
        self.close_today_note.clicked.connect(lambda: self.frame_note.setVisible(False))
        self.calendar2.clicked.connect(self.update_datetime2)
        self.save.clicked.connect(self.BACKKK3)
        self.save.clicked.connect(self.on_date_selected)
        self.save.clicked.connect(self.blink_page)
        
        
        
        

        self.time.setReadOnly(False)
        self.search_trash.textChanged.connect(self.hide_label)
        self.search_input.textChanged.connect(self.hide_label2)
        self.title_input.textChanged.connect(self.hide_label3)
        self.textEdiit.textChanged.connect(self.hide_label4)
        self.download.clicked.connect(check_update)
        
        
                
        
        if self.menu:
                self.menu.clicked.connect(self.toggle_left_bar)
                
        
       
                
        



        if self.Email:
            self.Email.clicked.connect(self.open_gmail_compose)
           

        self.update_calendar()
        

    # ====== Функции ======


    

    def load_today_events(self):
        print("load_today_events CALLED")
        
        # --- Очищаем панель событий полностью (виджеты и разделители) ---
        for i in reversed(range(self.event_layout.count())):
            item = self.event_layout.itemAt(i)
            widget_to_remove = item.widget() if item is not None else None
            if widget_to_remove:
                widget_to_remove.setParent(None)
            elif item is not None and item.spacerItem():
                self.event_layout.removeItem(item)

        import sqlite3
        from datetime import datetime
        from PySide6.QtCore import QDateTime
        from PySide6.QtWidgets import QLabel, QSpacerItem, QSizePolicy
        from PySide6.QtCore import Qt

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # --- Берём все напоминания, сортируем по remind_at ---
        c.execute("""
            SELECT id, title, text, remind_at
            FROM reminders
            ORDER BY remind_at ASC
        """)
        reminders = c.fetchall()
        conn.close()

        # --- Фильтруем только сегодняшние заметки ---
        today_str = datetime.now().strftime("%d-%m-%Y")
        today_reminders = []
        for r in reminders:
            note_id, title, text, remind_at = r
            if remind_at[:10] == today_str:  # сравниваем только дату
                today_reminders.append(r)

        if not today_reminders:
            # --- Если событий нет ---
            if self.language == "ru":
                label = QLabel("Событий нет")
            elif self.language == "en":
                label = QLabel("Events no")
            elif self.language == "qaz":
                label = QLabel("Оқиғалар жоқ")
            elif self.language == "corean":
                label = QLabel("이벤트가 없습니다")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: white; font-size: 18px;padding-right: 60px;")
            self.event_layout.addWidget(label)
            return

        self.note_cards.clear()

        for idx, reminder in enumerate(today_reminders):
            note_id, title, text, remind_at = reminder

            # --- Функция просмотра заметки ---
            def make_view_func1(note_id):
                def inner():
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("SELECT text, title, remind_at FROM reminders WHERE id = ?", (note_id,))
                    result = cursor.fetchone()
                    conn.close()

                    if result:
                        text, title, time_str = result
                        self.today_note_full_text_label.setText(text)
                        self.today_note_name.setText(title)

                        dt = QDateTime.fromString(time_str, "dd-MM-yyyy HH:mm")
                        if dt.isValid():
                            self.TIMEE2.setDateTime(dt)

                        self.frame_note.setVisible(True)
                        self.current_note_id2 = note_id
                return inner

            # --- Функция удаления ---
            def make_delete_func1(rem_id):
                def inner():
                    self.delete_reminder(rem_id)
                    self.load_today_events()
                return inner

            # --- Создаём мини-карточку ---
            card2 = MiniNoteCard(title, remind_at, make_view_func1(note_id), make_delete_func1(note_id))
            self.event_layout.addWidget(card2)
            self.note_cards.append(card2)
            panel_width = self.event_scroll.width()
            card2.setMaximumWidth(panel_width - 20)

            # --- Добавим отступ снизу ---
            if idx < len(today_reminders) - 1:
                spacer = QSpacerItem(0, 15, QSizePolicy.Minimum, QSizePolicy.Fixed)
                self.event_layout.addItem(spacer)






    
    

    def update_time_from_combo(self, time_str):
    # получаем текущее значение QDateTimeEdit
        current_dt = self.dataTIME2.dateTime()

        # разбиваем строку из комбо на часы и минуты
        hours, minutes = map(int, time_str.split(":"))

        # создаём новый QTime с выбранным временем
        current_dt.setTime(QtCore.QTime(hours, minutes))

        # ставим обратно в QDateTimeEdit
        self.dataTIME2.setDateTime(current_dt)


    def update_calendar(self):
        year = int(self.year_combo.currentText())
        month = self.month_combo.currentIndex() + 1
        day = min(self.calendar.selectedDate().day(), QDate(year, month, 1).daysInMonth())
        self.calendar.setSelectedDate(QDate(year, month, day))

    def update_calendar2(self):
        year = int(self.year.currentText())
        month = self.month.currentIndex() + 1
        day = min(self.calendar2.selectedDate().day(), QDate(year, month, 1).daysInMonth())
        self.calendar2.setSelectedDate(QDate(year, month, day))

    
    def Time(self):
        timE = self.time_combo


    def update_datetime2(self, qdate):
        # qdate — это объект QDate, который вернул календарь
        current_time = self.dataTIME2.time()  # оставляем текущее время
        self.dataTIME2.setDateTime(QDateTime(qdate, current_time))

    def update_date_time_edit(self):
        selected_date = self.calendar.selectedDate()
        self.date_time_edit.setDate(selected_date)

    def update_date_time_edit2(self):
        selected_date = self.calendar2.selectedDate()
        old_time = self.time2.time()  # сохраняем текущее время
        self.dataTIME2.setDateTime(QDateTime(selected_date, old_time))

    def time_change(self):
        current_date = self.dataTIME2.date()
        old_time = self.time2.time() 
        self.dataTIME2.setDateTime(QDateTime(current_date, old_time))

    


    def update_date_time_edit2(self):
        selected_date = self.calendar2.selectedDate()
        self.date_time_edit.setDate(selected_date)

    def update_time_from_timeedit(self, qtime):
        # Получаем текущее значение QDateTimeEdit
        current_dt = self.date_time_edit.dateTime()
        
        # Устанавливаем новое время из QTimeEdit
        current_dt.setTime(qtime)
        
        # Обновляем QDateTimeEdit
        self.date_time_edit.setDateTime(current_dt)


    def update_time_from_timeedit2(self, new_time):
        date = self.dataTIME2.date()
        self.dataTIME2.setDateTime(QDateTime(date, new_time))

    def update_current_datetime(self):
        now = QDateTime.currentDateTime()
        self.time.setDateTime(now)
        self.time.setReadOnly(True)


    def toggle_left_bar(self):
        self.frameleft.setVisible(False)
        self.menu2.setVisible(True)

    def save_note_changes(self):
        self.note_view_frame.setVisible(False)
        
           

        title = self.note_name.text()
        text = self.note_full_text_label.toPlainText()
        remind_at = self.TIMEE.dateTime().toString("dd-MM-yyyy HH:mm")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reminders SET title=?, text=?, remind_at=?, notified=0 WHERE id=?",
            (title, text, remind_at, self.current_note_id)
        )
        conn.commit()
        conn.close()

    def save_note_changes2(self):
        print("SAVE CALLED")

        if not hasattr(self, "current_note_id2"):
            print("ID НЕ УСТАНОВЛЕН")
            return

        title = self.today_note_name.text()
        text = self.today_note_full_text_label.toPlainText()
        remind_at = self.TIMEE2.dateTime().toString("dd-MM-yyyy HH:mm")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reminders SET title=?, text=?, remind_at=?, notified=0 WHERE id=?",
            (title, text, remind_at, self.current_note_id2)
        )
        conn.commit()
        conn.close()

        print("SAVED OK:", self.current_note_id2)
        self.load_today_events()
        
        

    def on_date_selected(self, qdate):
        
        # эта часть выполняется только после клика
        remind_at = self.dataTIME2.dateTime().toString("dd-MM-yyyy HH:mm")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reminders SET remind_at=?, notified=0 WHERE id=?",
            (remind_at, self.current_note_id)
        )
        conn.commit()
        conn.close()

        print("DEBUG: дата обновлена")
        self.MYY()

        # перезагружаем заметки
    def blink_page(self):
        current = self.stack.currentIndex()

        self.stack.setCurrentIndex(1)  # переключаемся на другую страницу

        QTimer.singleShot(1, lambda: self.stack.setCurrentIndex(current))

    def open_calendar(self, note_id):
        # сохраняем текущий note_id
        self.current_note_id = note_id

        # показываем календарь
        self.calendar2.setVisible(True)
        self.time2.setVisible(True)
        self.month.setVisible(True)
        self.year.setVisible(True)
        self.fr2.setVisible(True)


        # подключаем событие клика по дате
        self.calendar2.clicked.connect(self.on_date_selected)




    def expand_left_bar(self):
        
        """Анимация открытия"""
        self.menu2.setVisible(False)
        self.frameleft.setVisible(True)


   

        

    
    def clear_notes(self):
    # Удаляем все виджеты из контейнера с карточками
        while self.note_layout.count():
            item = self.note_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


    def animate_button(self, btn):
    # если есть предыдущая анимация — останавливаем её и сбрасываем
        if hasattr(btn, "animation") and btn.animation.state() == QPropertyAnimation.Running:
            btn.animation.stop()
            btn.setGeometry(btn.animation.endValue())  # вернуть геометрию в исходное положение

        rect = btn.geometry()
        anim = QPropertyAnimation(btn, b"geometry")
        anim.setDuration(150)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(rect)
        anim.setKeyValueAt(0.5, rect.adjusted(-2, -2, 2, 2))
        anim.setEndValue(rect)
        anim.start()
        btn.animation = anim
    

    
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve,QPoint

    def animate_card_in(self, widget, delay):
    # Запускаем анимацию с задержкой
        QTimer.singleShot(delay, lambda: self._start_card_animation(widget))

    def _start_card_animation(self, widget):
        anim = QPropertyAnimation(widget, b"pos")
        anim.setDuration(500)
        anim.setStartValue(widget.pos() - QPoint(50, 0))  # сдвиг слева
        anim.setEndValue(widget.pos())
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
    # Чтобы GC не удалил анимацию
        widget._animation = anim






    def HOMEE(self):
        self.stack.setCurrentIndex(1)
        self.animate_button(self.Home)
        self.load_today_events()
        self.load_notes()

    def NEWW(self):
        self.date_time_edit.setDateTime(QDateTime.currentDateTime())
        self.stack.setCurrentIndex(5)
        self.animate_button(self.Neww)

    

    def DELLALL(self):
        self.deleteall_forever()
        self.animate_button(self.delete_all)
        

        
        


    
            
        
    

    def poissk(self):
        self.poisk.setVisible(False)
                
    


    def Bs(self):
        self.animate_button(self.bss)
        self.stack.setCurrentIndex(3)
        self.load_trash()

    def Save_note(self):
    # Получаем заголовок и убираем пробелы
            self.HOMEE()
            title = self.title_input.text().strip()
            text2 = self.textEdiit.toPlainText().strip()

            # Если заголовок или текст пустой — не сохраняем
            if not title or not text2:
                QMessageBox.warning(
                    self,
                    "Предупреждение",
                    "Вы должны ввести название и текст заметки!"
                )
                return  # прекращаем выполнение функции

            # Даты напоминаний
            remind_at = self.date_time_edit.dateTime().toString("dd-MM-yyyy HH:mm")
            remind_at2 = self.date_time_edit3.dateTime().toString("dd-MM-yyyy HH:mm")

            # Текст заметки
            text = self.textEdiit.toPlainText().strip()

            # Сохраняем в базу данных
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reminders (title, text, remind_at, remind_at2) VALUES (?, ?, ?, ?)",
                (title, text, remind_at, remind_at2)
            )
            conn.commit()
            conn.close()

            # Обновляем интерфейс
            self.load_notes()
            self.load_today_events()
            self.animate_button(self.save_note)

            # Очищаем поля
            self.title_input.clear()
            self.textEdiit.clear()

            # Если есть функция для добавления напоминания в планировщик
            
            
                




    def load_notes(self):
        # --- Удаляем старые карточки ---
        for i in reversed(range(self.note_layout.count())):
            item = self.note_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
            elif item.spacerItem():
                self.note_layout.removeItem(item)

        self.note_cards.clear()

        # --- Загружаем данные из базы ---
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, title, text, remind_at, remind_at2, isDone FROM reminders")
        reminders = c.fetchall()
        conn.close()

        row = 0

        for idx, (note_id, title, text, remind_at, remind_at2, isDone) in enumerate(reminders):

            # ---------- VIEW ----------
            def make_view_func(note_id):
                def inner():
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT text, title, remind_at FROM reminders WHERE id = ?",
                        (note_id,)
                    )
                    result = cursor.fetchone()
                    conn.close()

                    if result:
                        text, title, time_str = result
                        self.note_name.setText(title)
                        self.note_full_text_label.setPlainText(text)

                        dt = QDateTime.fromString(time_str, "dd-MM-yyyy HH:mm")
                        if dt.isValid():
                            self.TIMEE.setDateTime(dt)
                            self.dataTIME2.setDateTime(dt)

                        self.note_view_frame.setVisible(True)
                        self.current_note_id = note_id
                return inner

            # ---------- DELETE ----------
            def make_delete_func(note_id):
                def inner():
                    self.delete_reminder(note_id)
                    self.load_notes()
                return inner

            # ---------- CARD ----------
            card = NoteCard(
                title,
                remind_at,
                remind_at2,
                make_view_func(note_id),
                make_delete_func(note_id)
            )

            card.change_date_btn.setVisible(True)

            # ---------- DONE ----------
            card.done_radio.blockSignals(True)
            card.done_radio.setChecked(bool(isDone))
            card.done_radio.blockSignals(False)
            card.back_btn.setVisible(False)

            card.done_radio.toggled.connect(
                lambda checked, rid=note_id: self.mark_done(rid, checked)
            )

            if isDone == 1:
                card.done_radio.setVisible(False)
                card.done_label.setVisible(False)
                card.done_label2.setVisible(True)

            # ---------- CHANGE DATE ----------
            card.change_date_btn.clicked.connect(
                lambda checked=False, rid=note_id: self.open_calendar(rid)
            )

            # ---------- LANGUAGE ----------
            card.languageb = self.language
            if self.language == "en":
                card.change_date_btn.setText("Change date")
                card.done_label.setText("Complete")
            elif self.language == "ru":
                card.change_date_btn.setText("Изменить дату")
                card.done_label.setText("Выполнено")
            elif self.language == "qaz":
                card.change_date_btn.setText("Күнді өзгерту")
                card.done_label.setText("Орындалды")
            elif self.language == "corean":
                card.change_date_btn.setText("날짜 변경")
                card.done_label.setText("완료됨")

            # ---------- ADD TO GRID ----------
            self.note_layout.addWidget(card, row, 0)
            self.note_cards.append(card)

            # spacer
            if idx < len(reminders) - 1:
                spacer = QSpacerItem(0, 15, QSizePolicy.Minimum, QSizePolicy.Fixed)
                self.note_layout.addItem(spacer, row + 1, 0)

            self.animate_card_in(card, idx * 100)

            row += 2

        self.note_layout.setRowStretch(row, 1)

                


        
    def mark_done(self, note_id, checked):
        isDone = 1 if checked else 0

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reminders SET isDone = ? WHERE id = ?",
            (isDone, note_id)
        )
        conn.commit()
        conn.close()

        # обновляем интерфейс
        self.load_notes()


    def delete_reminder(self, reminder_id):
    # Создаем сообщение
        msg = QMessageBox(self.ui)

        # Заголовок и текст в зависимости от языка
        if self.language == "ru":
            msg.setWindowTitle("Подтверждение удаления")
            msg.setText("Вы уверены, что хотите удалить эту заметку?")
            yes_text, no_text = "Да", "Нет"
        elif self.language == "en":
            msg.setWindowTitle("Confirm to delete")
            msg.setText("Are you sure you want to delete this note?")
            yes_text, no_text = "Yes", "No"
        elif self.language == "qaz":
            msg.setWindowTitle("Жоюды растау")
            msg.setText("Сіз бұл жазбаны жойғыңыз келетініне сенімдісіз бе?")
            yes_text, no_text = "Иә", "Жоқ"
        elif self.language == "corean":
            msg.setWindowTitle("삭제 확인")
            msg.setText("이 메모를 삭제하시겠습니까?")
            yes_text, no_text = "예", "아니요"

        # Добавляем кнопки
        yes_btn = msg.addButton(yes_text, QMessageBox.YesRole)
        no_btn = msg.addButton(no_text, QMessageBox.NoRole)
        msg.setDefaultButton(no_btn)

        msg.exec()

        # Если нажали не "Да" — выходим
        if msg.clickedButton() != yes_btn:
            return

        # ---- Удаляем заметку и переносим в корзину ----
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT title, text, remind_at, remind_at2 FROM reminders WHERE id = ?",
            (reminder_id,)
        )
        note = cursor.fetchone()

        if note:
            title, text, remind_at, remind_at2 = note
            deleted_at = datetime.now().strftime("%d-%m-%Y %H:%M")

            cursor.execute("""
                INSERT INTO trash 
                (title, text, remind_at, remind_at2, deleted_at, isDeleted, isDone)
                VALUES (?, ?, ?, ?, ?, 1, 0)
            """, (title, text, remind_at, remind_at2, deleted_at))

            cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

        conn.commit()
        conn.close()


    def load_trash(self):

        self.trash_scroll.setVisible(True)

        # Очищаем layout
        for i in reversed(range(self.trash_layout.count())):
            widget = self.trash_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        # ВАЖНО: берём isDone
        c.execute("""
            SELECT id, title, text, remind_at, remind_at2, isDone
            FROM trash
        """)
        trash_notes = c.fetchall()
        conn.close()

        for note_id, title, text, remind_at, remind_at2, isDone in trash_notes:

            def restore_func(n_id):
                def inner():
                    self.restore_from_trash(n_id)
                    self.load_trash()
                return inner

            def delete_forever_func(n_id):
                def inner():
                    self.delete_forever(n_id)
                    self.load_trash()
                return inner

            card = NoteCard(
                title,
                remind_at,
                remind_at2,
                restore_func(note_id),
                delete_forever_func(note_id)
            )

            # язык
            card.languageb = self.language

            # скрываем лишнее
            card.change_date_btn.setVisible(False)
            card.done_label.setVisible(False)
            card.done_radio.setVisible(False)
            card.view_btn.setVisible(False)

            # текст "Выполнено"
            if self.language == "en":
                card.done_label2.setText("Complete ✔️")
            elif self.language == "ru":
                card.done_label2.setText("Выполнено ✔️")
            elif self.language == "qaz":
                card.done_label2.setText("Орындалды ✔️")
            elif self.language == "corean":
                card.done_label2.setText("완료됨 ✔️")

            # ГЛАВНАЯ ЛОГИКА
            if isDone == 1:
                card.done_label2.setVisible(True)
            else:
                card.done_label2.setVisible(False)

            self.trash_layout.addWidget(card)


    def sync_combos_with_calendar(self, year, month):
        self.year_combo.setCurrentText(str(year))
        self.month_combo.setCurrentIndex(month - 1)

    def sync_combos_with_calendar2(self, year2, month2):
        self.year.setCurrentText(str(year2))
        self.month.setCurrentIndex(month2 - 1)

    def SETT(self):
        self.stack.setCurrentIndex(4)
        self.animate_button(self.setng)

    def engg(self):
        self.language = "en"
        self.animate_button(self.Eng)
        self.change_language("en")

    def hide_label(self):
            if self.search_trash.text().strip():
                self.poisk.hide()
            else:
                self.poisk.show()

    def hide_label3(self):
            if self.title_input.text().strip():
                self.Name.hide()
            else:
                self.Name.show()
    def hide_label4(self):
            if self.textEdiit.toPlainText().strip():
                self.Desc.hide()
            else:
                self.Desc.show()

    def hide_label2(self):
            if self.search_input.text().strip():
                self.poisk2.hide()
            else:
                self.poisk2.show()

    def ruu(self):
        self.language = "ru"
        self.animate_button(self.RU)
        self.change_language("ru")

    def qazz(self):
        self.language = "qaz"
        self.animate_button(self.QAZ)
        self.change_language("qaz")


    

    def cor(self):
        self.language = "corean"
        self.animate_button(self.corean)
        self.change_language("corean")


    def check_expired_notes(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        now = QDateTime.currentDateTime().toString("dd-MM-yyyy HH:mm")

    # Берём все просроченные заметки
        cursor.execute("SELECT id, title, text, remind_at FROM reminders WHERE remind_at <= ?", (now,))
        expired_notes = cursor.fetchall()

        for note_id, title, text, remind_at in expired_notes:
            deleted_at = datetime.now().strftime("%d-%m-%Y %H:%M")
        # Кладём в корзину
            cursor.execute("""
                INSERT INTO trash (title, text, remind_at, deleted_at) 
                VALUES (?, ?, ?, ?)
            """, (title, text, remind_at, deleted_at))
            # Удаляем из основной таблицы
            cursor.execute("DELETE FROM reminders WHERE id = ?", (note_id,))

        conn.commit()
        conn.close()

    # Обновляем интерфейс
        self.load_notes()
        self.load_today_events()
        self.load_trash()

    def MYY(self):
        self.stack.setCurrentIndex(2)
        self.animate_button(self.myy)
        self.load_notes()

    

    def search_notes(self):
        text = self.search_input.text().strip()  # убираем пробелы
        pattern = f"%{text}%"  # для LIKE

        # --- Очистка текущих карточек ---
        while self.note_layout.count():
            item = self.note_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.spacerItem():
                self.note_layout.removeItem(item)

        self.note_cards.clear()

        # --- Если поиск пустой, показываем все заметки ---
        if not text:
            self.load_notes()
            return

        # --- Подключаем базу ---
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, text, remind_at, remind_at2
            FROM reminders
            WHERE title LIKE ? COLLATE NOCASE OR text LIKE ? COLLATE NOCASE
        """, (pattern, pattern))

        results = cursor.fetchall()

        # --- Создаём карточки для найденных заметок ---
        for note_id, title, note_text, remind_at, remind_at2 in results:

            # Функция просмотра
            def make_view_func(nid=note_id):
                def inner():
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("SELECT text, title, remind_at FROM reminders WHERE id=?", (nid,))
                    result = c.fetchone()
                    conn.close()
                    if result:
                        text, title, time_str = result
                        self.note_full_text_label.setText(text)
                        self.note_name.setText(title)
                        dt = QDateTime.fromString(time_str, "dd-MM-yyyy HH:mm")
                        if dt.isValid():
                            self.TIMEE.setDateTime(dt)
                        self.note_view_frame.setVisible(True)
                return inner

            # Функция удаления
            def make_delete_func(nid=note_id):
                def inner():
                    self.delete_reminder(nid)
                    self.search_notes()  # обновляем поиск
                return inner

            # --- Создаём карточку ---
            card = NoteCard(title, remind_at, remind_at2, make_view_func(), make_delete_func())
            self.note_layout.addWidget(card)
            self.note_cards.append(card)

        # --- Прижимаем карточки к верху (если есть) ---
        if results:
            from PySide6.QtWidgets import QSpacerItem, QSizePolicy
            spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
            self.note_layout.addItem(spacer)
        if not results:
            self.load_notes()

        conn.close()
        
            
                                        
    def search_notes2(self):
        text = self.search_trash.text().lower().strip()

        # Очищаем текущие карточки
        while self.trash_layout.count():
            item = self.trash_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

    # Ищем в таблице trash
        cursor.execute("""
            SELECT id, title, text, remind_at,remind_at2
            FROM trash 
            WHERE LOWER(title) LIKE ? OR LOWER(text) LIKE ?
        """, (f"%{text}%", f"%{text}%"))

        trash_notes = cursor.fetchall()
        conn.close()

        for note_id, title, note_text, remind_at,remind_at2 in trash_notes:

            def restore_func(n_id):
                def inner():
                    self.restore_from_trash(n_id)
                    self.search_notes2()  # важно: обновляем именно корзину
                return inner

            def delete_forever_func(n_id):
                def inner():
                    self.delete_forever(n_id)
                    self.search_notes2()  # обновляем корзину
                return inner

            card = NoteCard(title, remind_at,remind_at2, restore_func(note_id), delete_forever_func(note_id))
            self.trash_layout.addWidget(card)























                     



    def restore_from_trash(self, trash_id):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT title, text, remind_at, remind_at2 FROM trash WHERE id = ?", (trash_id,))
        note = c.fetchone()

        if note:
            title, text, remind_at, remind_at2 = note
            c.execute("INSERT INTO reminders (title, text, remind_at,remind_at2) VALUES (?, ?, ?, ?)", (title, text, remind_at,remind_at2))
            c.execute("DELETE FROM trash WHERE id = ?", (trash_id,))

        conn.commit()
        conn.close()
        self.load_notes()

    def delete_forever(self, trash_id):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM trash WHERE id = ?", (trash_id,))
        conn.commit()
        conn.close()

    def deleteall_forever(self):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM trash")
        conn.commit()
        conn.close()
        self.trash_scroll.setVisible(False)





    def lightthema(self):
        self.framemain1 = self.ui.findChild(QWidget,"frame_container")
        self.frameright = self.ui.findChild(QFrame,"frame_9")
        self.frameleft = self.ui.findChild(QFrame,"frame_12")






        self.state = not self.state
        self.animate_button(self.light)
        if not self.state:
            self.stackedWidget1.setStyleSheet("background-color: rgb(0, 0, 0);")
            self.framemain1.setStyleSheet("background-color: rgb(0,0,0);")
            self.Neww.setStyleSheet("border-radius: 15px;background-color: rgb(46, 47, 49);color: rgb(255, 255, 255);")
            self.myy.setStyleSheet("border-radius: 15px;background-color: rgb(46, 47, 49);color: rgb(255, 255, 255);")
            self.bss.setStyleSheet("border-radius: 15px;background-color: rgb(46, 47, 49);color: rgb(255, 255, 255);")
            self.frameright.setStyleSheet("background-color: rgb(46, 47, 49);border-radius: 25px;")
            self.date_time_edit3.setStyleSheet("background-color: rgb(0, 0, 0);color: rgb(0,0,0);")
            
        else:
            self.stackedWidget1.setStyleSheet("background-color: rgb(255, 255, 255);")
            self.framemain1.setStyleSheet("background-color: rgb(255, 255, 255);")
            self.frameright.setStyleSheet("background-color: rgb(0,0,0);border-radius: 25px;")
            self.Neww.setStyleSheet("border-radius: 15px;background-color: rgb(0, 0, 0);color: rgb(255, 255, 255);")
            self.myy.setStyleSheet("border-radius: 15px;background-color: rgb(0, 0, 0);color: rgb(255, 255, 255);")
            self.bss.setStyleSheet("border-radius: 15px;background-color: rgb(0, 0, 0);color: rgb(255, 255, 255);")
            self.date_time_edit3.setStyleSheet("background-color: rgb(255, 255, 255);color: rgb(255,255,255);")
            
        

        


















       


    def BACKKK(self):
        self.month_combo.setVisible(False)
        self.calendar.setVisible(False)
        self.fr.setVisible(False)
        self.year_combo.setVisible(False)

    def BACKKK2(self):
        self.month_combo.setVisible(True)
        self.calendar.setVisible(True)
        self.year_combo.setVisible(True)
        self.fr.setVisible(True)
        self.animate_button(self.bac)

    def BACKKK3(self):
        self.time2.setVisible(False)
        self.month.setVisible(False)
        self.calendar2.setVisible(False)
        self.year.setVisible(False)
        self.fr2 = self.ui.findChild(QFrame,"fr2")
        self.fr2.setVisible(False)
        

    def open_gmail_compose(self):
        recipient_email = "khovinkirill@gmail.com"
        subject = "Пользователь"
        body = "Здравствуйте,\n\nОпишите вашу проблему или идею здесь."
        url = (
            "https://mail.google.com/mail/?view=cm&fs=1"
            f"&to={recipient_email}"
            f"&su={subject}"
            f"&body={body}"
        )
        self.animate_button(self.Email)
        webbrowser.open(url)



    #===========СМЕНА ЯЗЫКОВ===================


    




    def change_language(self, lang):
        for i in range(self.stackedWidget.count()):
            page = self.stackedWidget.widget(i)  # получаем страницу
            for w in page.findChildren(QWidget):
                name = w.objectName()
                if name in self.translations[lang] and hasattr(w, "setText"):
                    w.setText(self.translations[lang][name])



if __name__ == "__main__":
    init_db()

    app = QApplication(sys.argv)
    window = NoterraApp()

    # --- Устанавливаем фильтр событий ---
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtGui import QWindow
    check_update()
    if not BACKGROUND_FLAG:
        add_to_startup()

    class DebugFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show:
                if isinstance(obj, QWindow) and obj.objectName() == "QPushButtonClassWindow":
                    print("Скрываем лишнее окно!")
                    obj.hide()
            elif event.type() == QEvent.Show:
                if isinstance(obj, QWindow) and obj.objectName() == "QWidgetClassWindow":
                    print("Скрываем лишнее окно!")
                    obj.hide()
            
            return super().eventFilter(obj, event)


    debug_filter = DebugFilter()
    app.installEventFilter(debug_filter)

    # --- Запуск фоновой проверки напоминаний ---
    import threading
    threading.Thread(target=reminder_checker, daemon=True).start()

    sys.exit(app.exec())