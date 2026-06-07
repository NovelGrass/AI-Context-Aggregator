#!/usr/bin/env python3
"""
AI Context Aggregator – Main Entry Point
"""

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLineEdit, QFileDialog,
                             QTextEdit, QProgressBar, QLabel, QSplitter,
                             QCheckBox, QGroupBox, QComboBox, QTabWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from styles import ADOBE_CC_QSS
from workers import AggregatorWorker, ConversationWorker

__version__ = "1.0.0"
__author__ = "NovelGrass"
__license__ = "MIT"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AI Context Aggregator v{__version__}")
        self.resize(1100, 750)
        self.setStyleSheet(ADOBE_CC_QSS)
        self.worker = None
        self.init_ui()

    def init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # ========== TAB 1: FILE AGGREGATOR ==========
        agg_tab = QWidget()
        agg_layout = QVBoxLayout(agg_tab)
        agg_layout.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        agg_layout.addWidget(splitter)

        # Left panel (controls)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Input group
        grp_input = QGroupBox("1. Source (Folder or ZIP)")
        layout_input = QVBoxLayout()
        self.input_type = QComboBox()
        self.input_type.addItems(["Folder", "ZIP Archive"])
        self.input_type.currentTextChanged.connect(self.on_input_type_changed)
        self.agg_input_path = QLineEdit()
        self.agg_input_path.setPlaceholderText("Select folder or ZIP...")
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_agg_input)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Type:"))
        row1.addWidget(self.input_type)
        row1.addStretch()
        row2 = QHBoxLayout()
        row2.addWidget(self.agg_input_path)
        row2.addWidget(btn_browse)
        layout_input.addLayout(row1)
        layout_input.addLayout(row2)
        grp_input.setLayout(layout_input)
        left_layout.addWidget(grp_input)

        # Filters group
        grp_filters = QGroupBox("2. File Filters (optional)")
        layout_filters = QVBoxLayout()
        self.filter_enabled = QCheckBox("Enable custom filters")
        self.filter_enabled.setChecked(False)
        self.filter_enabled.toggled.connect(self.on_filter_toggled)
        self.include_patterns = QLineEdit()
        self.include_patterns.setPlaceholderText("Include: *.py, *.md, *.txt")
        self.exclude_patterns = QLineEdit()
        self.exclude_patterns.setPlaceholderText("Exclude: *test*, *.log")
        self.include_patterns.setEnabled(False)
        self.exclude_patterns.setEnabled(False)
        layout_filters.addWidget(self.filter_enabled)
        layout_filters.addWidget(QLabel("Include:"))
        layout_filters.addWidget(self.include_patterns)
        layout_filters.addWidget(QLabel("Exclude:"))
        layout_filters.addWidget(self.exclude_patterns)
        grp_filters.setLayout(layout_filters)
        left_layout.addWidget(grp_filters)

        # Options group
        grp_opts = QGroupBox("3. Processing Rules")
        layout_opts = QVBoxLayout()
        self.chk_gitignore = QCheckBox("Respect .gitignore")
        self.chk_gitignore.setChecked(True)
        self.chk_skip_binaries = QCheckBox("Skip binary/media files")
        self.chk_skip_binaries.setChecked(True)
        layout_opts.addWidget(self.chk_gitignore)
        layout_opts.addWidget(self.chk_skip_binaries)
        grp_opts.setLayout(layout_opts)
        left_layout.addWidget(grp_opts)

        # Output group
        grp_out = QGroupBox("4. Output")
        layout_out = QVBoxLayout()
        self.agg_output_format = QComboBox()
        self.agg_output_format.addItems([
            "Plain Text (.txt)",
            "Markdown (.md)",
            "XML Tagged (LLM optimised)"
        ])
        self.agg_output_format.currentTextChanged.connect(self.update_agg_output_extension)
        self.agg_output_path = QLineEdit()
        self.agg_output_path.setPlaceholderText("Output file path...")
        btn_out = QPushButton("Browse")
        btn_out.clicked.connect(self.browse_agg_output)
        row_out = QHBoxLayout()
        row_out.addWidget(self.agg_output_path)
        row_out.addWidget(btn_out)
        layout_out.addWidget(QLabel("Format:"))
        layout_out.addWidget(self.agg_output_format)
        layout_out.addWidget(QLabel("Save to:"))
        layout_out.addLayout(row_out)
        grp_out.setLayout(layout_out)
        left_layout.addWidget(grp_out)

        left_layout.addStretch()
        self.agg_process_btn = QPushButton("AGGREGATE FILES")
        self.agg_process_btn.setObjectName("PrimaryAction")
        self.agg_process_btn.clicked.connect(self.start_aggregation)
        left_layout.addWidget(self.agg_process_btn)

        splitter.addWidget(left)

        # Right panel (log)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        self.agg_log = QTextEdit()
        self.agg_log.setReadOnly(True)
        self.agg_progress = QProgressBar()
        self.agg_status = QLabel("Ready.")
        log_layout.addWidget(self.agg_status)
        log_layout.addWidget(self.agg_progress)
        log_layout.addWidget(self.agg_log)
        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group)
        splitter.addWidget(right)
        splitter.setSizes([350, 750])

        tabs.addTab(agg_tab, "File Aggregator")

        # ========== TAB 2: CONVERSATION REFORMATTER ==========
        conv_tab = QWidget()
        conv_layout = QVBoxLayout(conv_tab)
        conv_layout.setSpacing(15)

        # Input file
        grp_conv_in = QGroupBox("Input Conversation File")
        in_layout = QVBoxLayout()
        self.conv_input_path = QLineEdit()
        self.conv_input_path.setPlaceholderText("Select text file containing conversation...")
        btn_conv_in = QPushButton("Browse")
        btn_conv_in.clicked.connect(self.browse_conv_input)
        in_row = QHBoxLayout()
        in_row.addWidget(self.conv_input_path)
        in_row.addWidget(btn_conv_in)
        in_layout.addWidget(QLabel("Raw conversation file:"))
        in_layout.addLayout(in_row)
        grp_conv_in.setLayout(in_layout)
        conv_layout.addWidget(grp_conv_in)

        # Output settings
        grp_conv_out = QGroupBox("Output Settings")
        out_layout = QVBoxLayout()
        self.conv_output_format = QComboBox()
        self.conv_output_format.addItems([
            "Markdown (.md)",
            "Plain Text (.txt)",
            "XML Tagged (LLM optimised)"
        ])
        self.conv_output_format.currentTextChanged.connect(self.update_conv_output_extension)
        self.conv_output_path = QLineEdit()
        self.conv_output_path.setPlaceholderText("Output file path...")
        btn_conv_out = QPushButton("Browse")
        btn_conv_out.clicked.connect(self.browse_conv_output)
        out_row = QHBoxLayout()
        out_row.addWidget(self.conv_output_path)
        out_row.addWidget(btn_conv_out)
        out_layout.addWidget(QLabel("Format:"))
        out_layout.addWidget(self.conv_output_format)
        out_layout.addWidget(QLabel("Save to:"))
        out_layout.addLayout(out_row)
        grp_conv_out.setLayout(out_layout)
        conv_layout.addWidget(grp_conv_out)

        self.conv_process_btn = QPushButton("REFORMAT CONVERSATION FOR AI")
        self.conv_process_btn.setObjectName("PrimaryAction")
        self.conv_process_btn.clicked.connect(self.start_conversion)
        conv_layout.addWidget(self.conv_process_btn)

        # Log area
        conv_log_group = QGroupBox("Processing Log")
        conv_log_layout = QVBoxLayout()
        self.conv_log = QTextEdit()
        self.conv_log.setReadOnly(True)
        conv_log_layout.addWidget(self.conv_log)
        conv_log_group.setLayout(conv_log_layout)
        conv_layout.addWidget(conv_log_group)

        tabs.addTab(conv_tab, "Conversation Reformer")

    # ---------- Aggregator methods ----------
    def on_input_type_changed(self, text):
        if "Folder" in text:
            self.agg_input_path.setPlaceholderText("Select source folder...")
        else:
            self.agg_input_path.setPlaceholderText("Select ZIP archive...")

    def on_filter_toggled(self, enabled):
        self.include_patterns.setEnabled(enabled)
        self.exclude_patterns.setEnabled(enabled)

    def update_agg_output_extension(self):
        """Auto-update output file extension when format changes."""
        current = self.agg_output_path.text().strip()
        if not current:
            return
        path = Path(current)
        fmt = self.agg_output_format.currentText()
        if "Markdown" in fmt:
            new_ext = ".md"
        elif "XML" in fmt:
            new_ext = ".xml"
        else:
            new_ext = ".txt"
        new_path = path.with_suffix(new_ext)
        self.agg_output_path.setText(str(new_path))

    def browse_agg_input(self):
        if "Folder" in self.input_type.currentText():
            folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
            if folder:
                self.agg_input_path.setText(folder)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, "Select ZIP File", "", "ZIP Files (*.zip)")
            if file_path:
                self.agg_input_path.setText(file_path)

    def browse_agg_output(self):
        fmt = self.agg_output_format.currentText()
        if "Markdown" in fmt:
            ext = ".md"
        elif "XML" in fmt:
            ext = ".xml"
        else:
            ext = ".txt"
        default = f"aggregated_context{ext}"
        path, _ = QFileDialog.getSaveFileName(self, "Save Aggregated Output", default, f"*{ext}")
        if path:
            # Ensure correct extension
            if not path.endswith(ext):
                path += ext
            self.agg_output_path.setText(path)

    def log_agg(self, msg):
        self.agg_log.append(f"[{msg}]")
        self.agg_log.verticalScrollBar().setValue(self.agg_log.verticalScrollBar().maximum())

    def start_aggregation(self):
        in_path = self.agg_input_path.text().strip()
        out_path = self.agg_output_path.text().strip()
        if not in_path or not os.path.exists(in_path):
            self.log_agg("ERROR: Valid input required.")
            return
        if not out_path:
            self.log_agg("ERROR: Valid output path required.")
            return

        self.agg_process_btn.setEnabled(False)
        self.agg_process_btn.setText("PROCESSING...")
        self.agg_progress.setValue(0)
        self.agg_log.clear()

        fmt_text = self.agg_output_format.currentText()
        if "Markdown" in fmt_text:
            out_fmt = 'md'
        elif "XML" in fmt_text:
            out_fmt = 'xml'
        else:
            out_fmt = 'txt'

        options = {
            'respect_gitignore': self.chk_gitignore.isChecked(),
            'skip_binaries': self.chk_skip_binaries.isChecked(),
            'output_format': out_fmt,
            'filters_enabled': self.filter_enabled.isChecked(),
            'include_patterns': self.include_patterns.text(),
            'exclude_patterns': self.exclude_patterns.text()
        }

        self.worker = AggregatorWorker(in_path, out_path, options)
        self.worker.progress.connect(self.update_agg_progress)
        self.worker.log.connect(self.log_agg)
        self.worker.finished.connect(self.agg_finished)
        self.worker.start()

    def update_agg_progress(self, val, msg):
        self.agg_progress.setValue(val)
        self.agg_status.setText(msg)

    def agg_finished(self, out_path, success):
        self.agg_process_btn.setEnabled(True)
        self.agg_process_btn.setText("AGGREGATE FILES")
        if success:
            self.agg_status.setText(f"Success: {out_path}")
            self.log_agg(f"Saved to {out_path}")
        else:
            self.agg_status.setText("Processing failed.")

    # ---------- Conversation Reformer methods ----------
    def update_conv_output_extension(self):
        current = self.conv_output_path.text().strip()
        if not current:
            return
        path = Path(current)
        fmt = self.conv_output_format.currentText()
        if "Markdown" in fmt:
            new_ext = ".md"
        elif "XML" in fmt:
            new_ext = ".xml"
        else:
            new_ext = ".txt"
        new_path = path.with_suffix(new_ext)
        self.conv_output_path.setText(str(new_path))

    def browse_conv_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Conversation File", "",
                                              "Text Files (*.txt *.md);;All Files (*)")
        if path:
            self.conv_input_path.setText(path)

    def browse_conv_output(self):
        fmt = self.conv_output_format.currentText()
        if "Markdown" in fmt:
            ext = ".md"
        elif "XML" in fmt:
            ext = ".xml"
        else:
            ext = ".txt"
        default = f"ai_context_conversation{ext}"
        path, _ = QFileDialog.getSaveFileName(self, "Save AI-Ready Conversation", default, f"*{ext}")
        if path:
            if not path.endswith(ext):
                path += ext
            self.conv_output_path.setText(path)

    def log_conv(self, msg):
        self.conv_log.append(f"[{msg}]")
        self.conv_log.verticalScrollBar().setValue(self.conv_log.verticalScrollBar().maximum())

    def start_conversion(self):
        in_path = self.conv_input_path.text().strip()
        out_path = self.conv_output_path.text().strip()
        if not in_path or not os.path.exists(in_path):
            self.log_conv("ERROR: Please select a valid conversation file.")
            return
        if not out_path:
            self.log_conv("ERROR: Please specify an output file.")
            return

        self.conv_process_btn.setEnabled(False)
        self.conv_process_btn.setText("REFORMATTING...")
        self.conv_log.clear()

        fmt_text = self.conv_output_format.currentText()
        if "Markdown" in fmt_text:
            out_fmt = 'md'
        elif "XML" in fmt_text:
            out_fmt = 'xml'
        else:
            out_fmt = 'txt'

        self.worker = ConversationWorker(in_path, out_path, out_fmt)
        self.worker.log.connect(self.log_conv)
        self.worker.finished.connect(self.conv_finished)
        self.worker.start()

    def conv_finished(self, out_path, success):
        self.conv_process_btn.setEnabled(True)
        self.conv_process_btn.setText("REFORMAT CONVERSATION FOR AI")
        if success:
            self.log_conv(f"Success! AI‑ready context saved to: {out_path}")
        else:
            self.log_conv("Conversion failed. Check the input file format.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())