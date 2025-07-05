import sys
import os
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QTextEdit, QHBoxLayout, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

class ConvertWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal()

    def __init__(self, files):
        super().__init__()
        self.files = files

    def run(self):
        #calculate total number of files
        total = len(self.files)
        #determine ffmpeg path (bundled or system)
        if hasattr(sys, "_MEIPASS"):
            #pyinstaller bundle: use the included ffmpeg binary
            if sys.platform == "win32":
                ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe")
            elif sys.platform == "darwin":
                ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg")
            else:
                ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg")
        else:
            #fallback to system ffmpeg
            ffmpeg_path = "ffmpeg"
        for idx, file_path in enumerate(self.files, 1):
            #use .tmp.flac as the temporary file extension for ffmpeg compatibility
            tmp_path = file_path + ".tmp.flac"
            cmd = [
                ffmpeg_path, "-y", "-i", file_path,
                "-map_metadata", "0",
                "-sample_fmt", "s16", "-ar", "48000",
                tmp_path
            ]
            try:
                #run ffmpeg command and check for errors
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                #replace original file with converted file
                os.replace(tmp_path, file_path)
                self.status.emit(f"Converted (in-place): {os.path.basename(file_path)}")
            except subprocess.CalledProcessError as e:
                #handle ffmpeg errors and clean up temp file
                self.status.emit(f"Failed: {os.path.basename(file_path)}\n{e.stderr.decode()}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception as e:
                #handle other errors and clean up temp file
                self.status.emit(f"Error replacing file: {os.path.basename(file_path)}\n{str(e)}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            #update progress bar
            self.progress.emit(int(idx / total * 100))
        #notify user conversion is finished
        self.status.emit("Conversion finished.")
        self.finished.emit()

class FLACConverter(QWidget):
    def __init__(self):
        super().__init__()
        #set window title and size
        self.setWindowTitle("FLAC to 16bit 48000Hz Converter")
        self.resize(500, 350)
        self.selected_files = []
        self.worker_thread = None

        layout = QVBoxLayout()

        #info label for instructions
        self.info_label = QLabel("Select FLAC files or a folder containing FLAC files.")
        layout.addWidget(self.info_label)

        #file/folder selection buttons
        btn_layout = QHBoxLayout()
        self.file_btn = QPushButton("Select Files")
        self.file_btn.clicked.connect(self.select_files)
        btn_layout.addWidget(self.file_btn)

        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        btn_layout.addWidget(self.folder_btn)

        layout.addLayout(btn_layout)

        #save log and delete files buttons in the same row
        action_layout = QHBoxLayout()
        self.save_log_btn = QPushButton("Save Log")
        self.save_log_btn.clicked.connect(self.save_log)
        action_layout.addWidget(self.save_log_btn)

        self.delete_btn = QPushButton("Delete Files")
        self.delete_btn.clicked.connect(self.delete_files)
        self.delete_btn.setEnabled(False)
        action_layout.addWidget(self.delete_btn)

        layout.addLayout(action_layout)

        #convert button in its own row just below the other buttons, above the progress bar
        convert_layout = QHBoxLayout()
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.clicked.connect(self.convert_files)
        self.convert_btn.setEnabled(False)
        convert_layout.addWidget(self.convert_btn)
        layout.addLayout(convert_layout)

        #progress bar
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress)

        #file list display
        self.file_list = QTextEdit()
        self.file_list.setReadOnly(True)
        layout.addWidget(self.file_list)

        #status/log display
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        layout.addWidget(self.status)

        self.setLayout(layout)

    def update_file_list(self):
        #update the file list box with selected files
        if self.selected_files:
            self.file_list.setPlainText('\n'.join(self.selected_files))
            self.delete_btn.setEnabled(True)
        else:
            self.file_list.setPlainText('')
            self.delete_btn.setEnabled(False)

    def select_files(self):
        #open file dialog for selecting flac files
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select FLAC Files", "", "FLAC Files (*.flac)"
        )
        if files:
            self.selected_files = files
            self.info_label.setText(f"Selected {len(files)} file(s).")
            self.convert_btn.setEnabled(True)
        else:
            self.selected_files = []
            self.info_label.setText("Select FLAC files or a folder containing FLAC files.")
            self.convert_btn.setEnabled(False)
        self.update_file_list()

    def select_folder(self):
        #open folder dialog and find all flac files recursively
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            flac_files = []
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith('.flac'):
                        flac_files.append(os.path.join(root, file))
            self.selected_files = flac_files
            self.info_label.setText(f"Found {len(flac_files)} FLAC file(s) in folder.")
            self.convert_btn.setEnabled(bool(flac_files))
        else:
            self.selected_files = []
            self.info_label.setText("Select FLAC files or a folder containing FLAC files.")
            self.convert_btn.setEnabled(False)
        self.update_file_list()

    def convert_files(self):
        #start conversion in a worker thread
        if not self.selected_files:
            self.status.append("No files selected.")
            return
        self.status.append("Starting conversion...")
        self.progress.setValue(0)
        self.convert_btn.setEnabled(False)
        self.file_btn.setEnabled(False)
        self.folder_btn.setEnabled(False)

        self.worker = ConvertWorker(self.selected_files)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.status.append)
        self.worker.finished.connect(self.on_conversion_finished)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def on_conversion_finished(self):
        #re-enable buttons and set progress to 100%
        self.convert_btn.setEnabled(True)
        self.file_btn.setEnabled(True)
        self.folder_btn.setEnabled(True)
        self.progress.setValue(100)

    def save_log(self):
        #save the status log to a file
        filename, _ = QFileDialog.getSaveFileName(self, "Save Log", "conversion_log.txt", "Text Files (*.txt);;All Files (*)")
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.status.toPlainText())

    def delete_files(self):
        #delete all selected files and update UI
        deleted = 0
        for file_path in self.selected_files:
            try:
                os.remove(file_path)
                deleted += 1
                self.status.append(f"Deleted: {os.path.basename(file_path)}")
            except Exception as e:
                self.status.append(f"Failed to delete: {os.path.basename(file_path)}\n{str(e)}")
        self.status.append(f"Deleted {deleted} file(s).")
        self.selected_files = []
        self.update_file_list()
        self.info_label.setText("Select FLAC files or a folder containing FLAC files.")
        self.convert_btn.setEnabled(False)

if __name__ == "__main__":
    #run the Qt application
    app = QApplication(sys.argv)
    window = FLACConverter()
    window.show()
    sys.exit(app.exec())
