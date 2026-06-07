# STYLESHEET (Inspired by Adobe Photoshop UI – no copyrighted assets)
ADOBE_CC_QSS = """
    QMainWindow, QWidget {
        background-color: #1E1E1E;
        color: #CCCCCC;
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }
    QGroupBox {
        background-color: #252526;
        border: 1px solid #3E3E42;
        border-radius: 4px;
        margin-top: 12px;
        font-weight: bold;
        color: #E0E0E0;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        color: #0078D4;
    }
    QPushButton {
        background-color: #3E3E42;
        color: #FFFFFF;
        border: 1px solid #555555;
        border-radius: 3px;
        padding: 6px 12px;
        font-weight: 600;
    }
    QPushButton:hover {
        background-color: #505055;
        border: 1px solid #0078D4;
    }
    QPushButton:pressed {
        background-color: #0078D4;
    }
    QPushButton#PrimaryAction {
        background-color: #0078D4;
        border: 1px solid #0078D4;
        color: #FFFFFF;
        font-size: 14px;
        padding: 8px 16px;
    }
    QPushButton#PrimaryAction:hover {
        background-color: #1084D9;
    }
    QLineEdit, QTextEdit {
        background-color: #2D2D30;
        border: 1px solid #3E3E42;
        border-radius: 3px;
        color: #CCCCCC;
        padding: 6px;
        selection-background-color: #0078D4;
    }
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid #0078D4;
    }
    QProgressBar {
        border: 1px solid #3E3E42;
        border-radius: 3px;
        text-align: center;
        background-color: #2D2D30;
        color: #CCCCCC;
    }
    QProgressBar::chunk {
        background-color: #0078D4;
        border-radius: 2px;
    }
    QLabel { color: #AAAAAA; }
    QScrollBar:vertical {
        border: none;
        background: #1E1E1E;
        width: 10px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #424242;
        min-height: 20px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover { background: #555555; }
"""