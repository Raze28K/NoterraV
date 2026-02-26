from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QGraphicsDropShadowEffect, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QColor


class MiniNoteCard(QFrame):
    def __init__(self, title, remind_at, on_view_clicked=None, on_delete_clicked=None):
        super().__init__()

        # --- Тень ---
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        # --- Стиль ---
        self.setStyleSheet("""
            QFrame {
                background-color: #2c2c2e;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            QLabel {
                color: #fff;
                background: transparent;
            }
            QLabel#DateLabel {
                font-size: 13px;
                color: #aaa;
            }
            QLabel#TitleLabel {
                font-size: 15px;
                font-weight: 500;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
            }
        """)

        self.setFixedHeight(60)  # ниже и компактнее
        self.setMinimumWidth(100)

        # --- Элементы ---
        date_label = QLabel(remind_at)
        date_label.setObjectName("DateLabel")

        title_label = QLabel(title)
        title_label.setObjectName("TitleLabel")
        title_label.setWordWrap(True)

        view_btn = QPushButton()
        view_btn.setIcon(QIcon("images/icons/cil-pencil.png"))
        view_btn.setFixedSize(28, 28)

        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(28, 28)

        if on_view_clicked:
            view_btn.clicked.connect(on_view_clicked)
        if on_delete_clicked:
            delete_btn.clicked.connect(on_delete_clicked)

        # --- Текст слева ---
        text_layout = QVBoxLayout()
        text_layout.addWidget(date_label)
        text_layout.addWidget(title_label)
        text_layout.setSpacing(2)

        # --- Кнопки справа ---
        button_layout = QVBoxLayout()
        button_layout.addWidget(view_btn)
        button_layout.addWidget(delete_btn)
        button_layout.setSpacing(4)
        button_layout.setAlignment(Qt.AlignCenter)

        # --- Главный layout ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 6, 10, 6)
        main_layout.setSpacing(8)
        main_layout.addLayout(text_layout)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)

        
