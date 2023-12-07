from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import (
    QMainWindow,
)

from ui.main_window import Ui_MainWindow

app = QApplication([])
window = QMainWindow()
ui = Ui_MainWindow()
ui.setupUi(window)

ui.slider_timeline.setStyleSheet("""
QSlider::groove:horizontal {
    background: #ddd;
}
QSlider::handle:horizontal {
    background: qlineargradient(
        x1:0, y1:0,
        x2:1, y2:1,
        stop:0 #f06,
        stop:1 #333
    );
    border: 1px solid #777;
    width: 18px; margin: -2px 0;
}
""")

window.show()
app.exec()
