import sys
import requests
from PySide6.QtWidgets import QApplication, QMessageBox
import webbrowser

APP_VERSION = "0.9.0"

def check_update():
    try:
        # Запрашиваем конкретный тег 'app'
        url = "https://api.github.com/repos/Raze28K/Nottera/releases/tags/app"
        data = requests.get(url).json()

        latest_version = data.get("tag_name", "app").replace("v","")

        if latest_version != APP_VERSION:
            msg = QMessageBox()
            msg.setWindowTitle("Обновление Noterra")
            msg.setText(f"Доступно новое обновление {latest_version}")

            download = msg.addButton("Скачать", QMessageBox.AcceptRole)
            later = msg.addButton("Позже", QMessageBox.RejectRole)

            msg.exec()

            if msg.clickedButton() == download:
                webbrowser.open(data["html_url"])

        else:
            QMessageBox.information(None, "Обновление", "Обновлений нет")

    except Exception as e:
        print("Ошибка проверки обновления:", e)

app = QApplication(sys.argv)
check_update()