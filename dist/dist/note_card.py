from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QPushButton, QRadioButton,
    QVBoxLayout, QHBoxLayout, QScrollArea, QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QColor
import sys

class NoteCard(QFrame):
    def __init__(self, title, remind_at, remind_at2, on_view_clicked, on_delete_clicked):
        super().__init__()

        # --- Мягкая тень ---
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        # --- Стиль ---
        self.setStyleSheet("""
            QFrame {
                background-color: #1c1c1e;
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QLabel#DateLabel, QLabel#DateLabel2 {
                color: #ffffff;
                font-size: 14px;
                border: none;
            }
            QLabel#TitleLabel {
                color: #ffffff;
                font-size: 18px;
                font-weight: 500;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #fff;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.18);
            }
        """)

        # --- Фиксированная высота и политика размера ---
        self.setFixedHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(380)

        # --- Даты ---
        done_label_text = QLabel("Дата выполнения:")
        done_label_text.setStyleSheet("color: #aaa; font-size: 14px; border: none;")
        date_label = QLabel(remind_at)
        date_label.setObjectName("DateLabel")

        done_layout_dates = QHBoxLayout()
        done_layout_dates.addWidget(done_label_text)
        done_layout_dates.addWidget(date_label)
        done_layout_dates.addStretch()

        created_label = QLabel("Дата создания:")
        created_label.setStyleSheet("color: #aaa; font-size: 14px; border: none;")
        date_label2 = QLabel(remind_at2)
        date_label2.setObjectName("DateLabel2")
        date_label2.setContentsMargins(5, 0, 0, 0)

        created_layout = QHBoxLayout()
        created_layout.addWidget(created_label)
        created_layout.addWidget(date_label2)
        created_layout.addStretch()

        # --- Заголовок ---
        title_label = QLabel(title)
        title_label.setObjectName("TitleLabel")
        title_label.setWordWrap(True)

        # --- Кнопки ---
        self.view_btn = QPushButton()
        self.back_btn = QPushButton()
        self.view_btn.setIcon(QIcon("images/icons/cil-pencil.png"))
        self.back_btn.setIcon(QIcon("images/icons/cil-chevron-circle-left-alt.png"))
        delete_btn = QPushButton("❌")
        for btn in (self.view_btn, delete_btn,self.back_btn):
            btn.setFixedSize(36, 36)
        self.view_btn.clicked.connect(on_view_clicked)
        self.back_btn.clicked.connect(on_view_clicked)

        delete_btn.clicked.connect(on_delete_clicked)

        button_layout = QVBoxLayout()
        button_layout.addWidget(self.view_btn)
        button_layout.addWidget(self.back_btn)
        button_layout.addWidget(delete_btn)
        button_layout.setSpacing(8)
        button_layout.setAlignment(Qt.AlignCenter)

        # --- Левый текстовый блок ---
        text_layout = QVBoxLayout()
        text_layout.addLayout(done_layout_dates)
        text_layout.addLayout(created_layout)
        text_layout.addWidget(title_label)
        text_layout.setSpacing(10)

        # --- Нижний ряд с радио и датой ---
        self.done_radio = QRadioButton()
        self.done_radio.setAutoExclusive(False)
        self.done_radio.toggled.connect(self.on_done_toggled)
        self.done_radio.setStyleSheet("""
            QRadioButton {
                spacing: 0px;
                background: transparent;
            }
            QRadioButton::indicator {
                width: 22px;
                height: 22px;
                border-radius: 11px;
                border: 2px solid #666;
                background-color: transparent;
            }
            QRadioButton::indicator:hover {
                border: 2px solid #aaa;
            }
            QRadioButton::indicator:checked {
                background-color: #00ff88;
                border: 2px solid #00ff88;
            }
            QRadioButton::indicator:checked::after {
                content: "";
                width: 10px;
                height: 10px;
                margin: 4px;
                border-radius: 5px;
                background-color: #0f0f0f;
            }
        """)
        self.done_label = QLabel("Выполнено")
        self.done_label2 = QLabel("Выполнено✔️")
        self.done_label2.setVisible(False)
        self.done_label.setStyleSheet("color: #fff; font-size: 14px; border: none;")

        self.change_date_btn = QPushButton("Изменить дату")
        self.change_date_btn.setFixedHeight(28)
        self.change_date_btn.setStyleSheet(
            "color: #fff; background-color: rgba(255,255,255,0.1); border-radius: 6px;"
        )

        done_layout = QHBoxLayout()
        done_layout.addWidget(self.done_radio)
        done_layout.addWidget(self.done_label)
        done_layout.addWidget(self.done_label2)
        done_layout.addWidget(self.change_date_btn)
        done_layout.addStretch()

        # --- Верхний ряд ---
        top_layout = QHBoxLayout()
        top_layout.addLayout(text_layout)
        top_layout.addStretch()
        top_layout.addLayout(button_layout)

        # --- Главный layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(done_layout)

    def on_done_toggled(self, checked: bool):
        self.done_label2.setVisible(checked)
