#!/usr/bin/env python3
"""
AI Context Aggregator – Main Entry Point
v2.1 - Fixed XML output, added HTML graph format, PNG export works.
"""

import sys
import os
import json
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLineEdit, QFileDialog,
                             QTextEdit, QProgressBar, QLabel, QSplitter,
                             QCheckBox, QGroupBox, QComboBox, QTabWidget,
                             QSpinBox, QDoubleSpinBox, QMessageBox, QInputDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QAction, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView

from styles import ADOBE_CC_QSS
from workers import AggregatorWorker, ConversationWorker, GraphWorker, ExplainerWorker

__version__ = "2.1.0"
__author__ = "NovelGrass"
__license__ = "MIT"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AI Context Aggregator v{__version__}")
        self.resize(1300, 850)
        self.setStyleSheet(ADOBE_CC_QSS)
        self.worker = None
        self.last_graph_data = None  # (nodes, edges)
        self.last_graph_base = None
        self.init_ui()
        self.load_presets()

    def init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # ========== TAB 1: FILE AGGREGATOR ==========
        agg_tab = QWidget()
        agg_layout = QVBoxLayout(agg_tab)
        agg_layout.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        agg_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

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

        # Preset filters
        grp_preset = QGroupBox("Filter Presets")
        preset_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Custom", "Python Project", "Web App (JS/TS/HTML/CSS)", "Documentation (MD/TXT)", "Full Codebase"])
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        btn_save_preset = QPushButton("Save Current as Preset")
        btn_save_preset.clicked.connect(self.save_current_preset)
        preset_layout.addWidget(QLabel("Preset:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addWidget(btn_save_preset)
        grp_preset.setLayout(preset_layout)
        left_layout.addWidget(grp_preset)

        # Filters
        grp_filters = QGroupBox("2. File Filters")
        layout_filters = QVBoxLayout()
        self.filter_enabled = QCheckBox("Enable custom filters")
        self.filter_enabled.setChecked(True)
        self.include_patterns = QLineEdit()
        self.include_patterns.setPlaceholderText("Include patterns (comma-separated, e.g. *.py, *.md)")
        self.exclude_patterns = QLineEdit()
        self.exclude_patterns.setPlaceholderText("Exclude patterns (e.g. *test*, *.log)")
        layout_filters.addWidget(self.filter_enabled)
        layout_filters.addWidget(QLabel("Include:"))
        layout_filters.addWidget(self.include_patterns)
        layout_filters.addWidget(QLabel("Exclude:"))
        layout_filters.addWidget(self.exclude_patterns)
        grp_filters.setLayout(layout_filters)
        left_layout.addWidget(grp_filters)

        # Options
        grp_opts = QGroupBox("3. Processing Rules")
        layout_opts = QVBoxLayout()
        self.chk_gitignore = QCheckBox("Respect .gitignore")
        self.chk_gitignore.setChecked(True)
        self.chk_skip_binaries = QCheckBox("Skip binary/media files")
        self.chk_skip_binaries.setChecked(True)
        self.chk_token_count = QCheckBox("Show detailed token counts (GPT-4, Claude, Gemini)")
        self.chk_token_count.setChecked(True)
        layout_opts.addWidget(self.chk_gitignore)
        layout_opts.addWidget(self.chk_skip_binaries)
        layout_opts.addWidget(self.chk_token_count)
        grp_opts.setLayout(layout_opts)
        left_layout.addWidget(grp_opts)

        # Output
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

        conv_log_group = QGroupBox("Processing Log")
        conv_log_layout = QVBoxLayout()
        self.conv_log = QTextEdit()
        self.conv_log.setReadOnly(True)
        conv_log_layout.addWidget(self.conv_log)
        conv_log_group.setLayout(conv_log_layout)
        conv_layout.addWidget(conv_log_group)

        tabs.addTab(conv_tab, "Conversation Reformer")

        # ========== TAB 3: KNOWLEDGE GRAPH ==========
        graph_tab = QWidget()
        graph_layout = QVBoxLayout(graph_tab)
        graph_layout.setContentsMargins(10, 10, 10, 10)

        graph_splitter = QSplitter(Qt.Orientation.Horizontal)
        graph_layout.addWidget(graph_splitter)

        graph_left = QWidget()
        graph_left_layout = QVBoxLayout(graph_left)
        graph_left_layout.setContentsMargins(0, 0, 0, 0)

        grp_graph_input = QGroupBox("1. Source (Folder or ZIP)")
        graph_input_layout = QVBoxLayout()
        self.graph_input_type = QComboBox()
        self.graph_input_type.addItems(["Folder", "ZIP Archive"])
        self.graph_input_type.currentTextChanged.connect(self.on_graph_input_type_changed)
        self.graph_input_path = QLineEdit()
        self.graph_input_path.setPlaceholderText("Select folder or ZIP...")
        btn_graph_browse = QPushButton("Browse")
        btn_graph_browse.clicked.connect(self.browse_graph_input)

        row_g1 = QHBoxLayout()
        row_g1.addWidget(QLabel("Type:"))
        row_g1.addWidget(self.graph_input_type)
        row_g1.addStretch()
        row_g2 = QHBoxLayout()
        row_g2.addWidget(self.graph_input_path)
        row_g2.addWidget(btn_graph_browse)
        graph_input_layout.addLayout(row_g1)
        graph_input_layout.addLayout(row_g2)
        grp_graph_input.setLayout(graph_input_layout)
        graph_left_layout.addWidget(grp_graph_input)

        # Extraction options
        grp_graph_opts = QGroupBox("2. Extraction Options")
        graph_opts_layout = QVBoxLayout()
        self.chk_extract_symbols = QCheckBox("Extract code symbols (functions, classes)")
        self.chk_extract_symbols.setChecked(True)
        self.chk_extract_calls = QCheckBox("Extract function calls (cross-file)")
        self.chk_extract_calls.setChecked(True)
        self.chk_extract_markdown = QCheckBox("Extract noun phrases / topics from Markdown/Text")
        self.chk_extract_markdown.setChecked(True)
        self.chk_extract_entities = QCheckBox("Extract named entities from PDF/DOCX")
        self.chk_extract_entities.setChecked(True)
        self.chk_extract_references = QCheckBox("Detect cross-file imports")
        self.chk_extract_references.setChecked(True)
        self.chk_extract_dir_hierarchy = QCheckBox("Include directory hierarchy")
        self.chk_extract_dir_hierarchy.setChecked(True)
        graph_opts_layout.addWidget(self.chk_extract_symbols)
        graph_opts_layout.addWidget(self.chk_extract_calls)
        graph_opts_layout.addWidget(self.chk_extract_markdown)
        graph_opts_layout.addWidget(self.chk_extract_entities)
        graph_opts_layout.addWidget(self.chk_extract_references)
        graph_opts_layout.addWidget(self.chk_extract_dir_hierarchy)
        grp_graph_opts.setLayout(graph_opts_layout)
        graph_left_layout.addWidget(grp_graph_opts)

        # Graph customization
        grp_graph_custom = QGroupBox("3. Graph Customization")
        custom_layout = QVBoxLayout()
        row_max = QHBoxLayout()
        row_max.addWidget(QLabel("Max nodes:"))
        self.graph_max_nodes = QSpinBox()
        self.graph_max_nodes.setRange(10, 10000)
        self.graph_max_nodes.setValue(500)
        row_max.addWidget(self.graph_max_nodes)
        row_max.addStretch()
        custom_layout.addLayout(row_max)

        row_thresh = QHBoxLayout()
        row_thresh.addWidget(QLabel("Strength threshold:"))
        self.graph_threshold = QDoubleSpinBox()
        self.graph_threshold.setRange(0.0, 1.0)
        self.graph_threshold.setSingleStep(0.05)
        self.graph_threshold.setValue(0.1)
        row_thresh.addWidget(self.graph_threshold)
        row_thresh.addStretch()
        custom_layout.addLayout(row_thresh)

        row_focus = QHBoxLayout()
        row_focus.addWidget(QLabel("Focus file types:"))
        self.graph_focus_types = QLineEdit()
        self.graph_focus_types.setPlaceholderText("e.g., .py,.md,.txt")
        row_focus.addWidget(self.graph_focus_types)
        custom_layout.addLayout(row_focus)
        grp_graph_custom.setLayout(custom_layout)
        graph_left_layout.addWidget(grp_graph_custom)

        # Output and actions
        grp_graph_out = QGroupBox("4. Output & Actions")
        graph_out_layout = QVBoxLayout()
        self.graph_output_format = QComboBox()
        self.graph_output_format.addItems([
            "JSON-LD (schema.org)",
            "GraphML (Gephi/networkx)",
            "CSV (nodes.csv + edges.csv)",
            "HTML (Interactive graph)"
        ])
        self.graph_output_format.currentTextChanged.connect(self.update_graph_output_extension)
        self.graph_output_path = QLineEdit()
        self.graph_output_path.setPlaceholderText("Output file path...")
        btn_graph_out = QPushButton("Browse")
        btn_graph_out.clicked.connect(self.browse_graph_output)
        row_gout = QHBoxLayout()
        row_gout.addWidget(self.graph_output_path)
        row_gout.addWidget(btn_graph_out)
        graph_out_layout.addWidget(QLabel("Format:"))
        graph_out_layout.addWidget(self.graph_output_format)
        graph_out_layout.addWidget(QLabel("Save to:"))
        graph_out_layout.addLayout(row_gout)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.view_graph_btn = QPushButton("VIEW GRAPH (Embedded)")
        self.view_graph_btn.setEnabled(False)
        self.view_graph_btn.clicked.connect(self.open_embedded_viewer)
        btn_layout.addWidget(self.view_graph_btn)
        self.detect_cycles_btn = QPushButton("DETECT CIRCULAR DEPENDENCIES")
        self.detect_cycles_btn.setEnabled(False)
        self.detect_cycles_btn.clicked.connect(self.detect_cycles)
        btn_layout.addWidget(self.detect_cycles_btn)
        graph_out_layout.addLayout(btn_layout)

        grp_graph_out.setLayout(graph_out_layout)
        graph_left_layout.addWidget(grp_graph_out)

        graph_left_layout.addStretch()
        self.graph_process_btn = QPushButton("BUILD KNOWLEDGE GRAPH")
        self.graph_process_btn.setObjectName("PrimaryAction")
        self.graph_process_btn.clicked.connect(self.start_graph_build)
        graph_left_layout.addWidget(self.graph_process_btn)

        graph_splitter.addWidget(graph_left)

        graph_right = QWidget()
        graph_right_layout = QVBoxLayout(graph_right)
        graph_log_group = QGroupBox("Graph Building Log")
        graph_log_layout = QVBoxLayout()
        self.graph_log = QTextEdit()
        self.graph_log.setReadOnly(True)
        self.graph_progress = QProgressBar()
        self.graph_status = QLabel("Ready.")
        graph_log_layout.addWidget(self.graph_status)
        graph_log_layout.addWidget(self.graph_progress)
        graph_log_layout.addWidget(self.graph_log)
        graph_log_group.setLayout(graph_log_layout)
        graph_right_layout.addWidget(graph_log_group)
        graph_splitter.addWidget(graph_right)
        graph_splitter.setSizes([450, 750])

        tabs.addTab(graph_tab, "Knowledge Graph")

        # ========== TAB 4: CODEBASE EXPLAINER ==========
        explainer_tab = QWidget()
        explainer_layout = QVBoxLayout(explainer_tab)

        exp_input_group = QGroupBox("Codebase Source")
        exp_input_layout = QHBoxLayout()
        self.exp_input_path = QLineEdit()
        self.exp_input_path.setPlaceholderText("Select folder or ZIP...")
        btn_exp_browse = QPushButton("Browse")
        btn_exp_browse.clicked.connect(self.browse_exp_input)
        exp_input_layout.addWidget(self.exp_input_path)
        exp_input_layout.addWidget(btn_exp_browse)
        exp_input_group.setLayout(exp_input_layout)
        explainer_layout.addWidget(exp_input_group)

        exp_opts_group = QGroupBox("Explain Options")
        exp_opts_layout = QVBoxLayout()
        self.exp_include_arch = QCheckBox("Describe architecture and dependencies")
        self.exp_include_arch.setChecked(True)
        self.exp_include_entry = QCheckBox("Identify entry points (main, app, etc.)")
        self.exp_include_entry.setChecked(True)
        self.exp_include_dataflow = QCheckBox("Infer data flow (imports, calls)")
        self.exp_include_dataflow.setChecked(True)
        self.exp_max_files = QSpinBox()
        self.exp_max_files.setRange(1, 500)
        self.exp_max_files.setValue(50)
        exp_opts_layout.addWidget(self.exp_include_arch)
        exp_opts_layout.addWidget(self.exp_include_entry)
        exp_opts_layout.addWidget(self.exp_include_dataflow)
        exp_opts_layout.addWidget(QLabel("Max files to analyze:"))
        exp_opts_layout.addWidget(self.exp_max_files)
        exp_opts_group.setLayout(exp_opts_layout)
        explainer_layout.addWidget(exp_opts_group)

        self.exp_generate_btn = QPushButton("GENERATE CODEBASE EXPLANATION")
        self.exp_generate_btn.setObjectName("PrimaryAction")
        self.exp_generate_btn.clicked.connect(self.start_explanation)
        explainer_layout.addWidget(self.exp_generate_btn)

        self.exp_output = QTextEdit()
        self.exp_output.setReadOnly(True)
        self.exp_output.setPlaceholderText("LLM-ready explanation will appear here...")
        explainer_layout.addWidget(self.exp_output)

        tabs.addTab(explainer_tab, "Codebase Explainer")

    # ---------- Aggregator methods ----------
    def load_presets(self):
        self.presets_file = Path.home() / ".ai_context_aggregator_presets.json"
        self.custom_presets = {}
        if self.presets_file.exists():
            try:
                with open(self.presets_file, 'r') as f:
                    self.custom_presets = json.load(f)
                for name in self.custom_presets:
                    self.preset_combo.addItem(name)
            except:
                pass

    def apply_preset(self, preset_name):
        if preset_name == "Custom":
            return
        presets = {
            "Python Project": {"include": "*.py, *.ipynb, requirements.txt", "exclude": "*test*, *__pycache__*, *.pyc"},
            "Web App (JS/TS/HTML/CSS)": {"include": "*.js, *.ts, *.html, *.css, *.json", "exclude": "node_modules/*, dist/*, build/*"},
            "Documentation (MD/TXT)": {"include": "*.md, *.txt, *.rst, *.tex", "exclude": ""},
            "Full Codebase": {"include": "*", "exclude": "*.log, *.tmp, *.cache"}
        }
        if preset_name in self.custom_presets:
            inc = self.custom_presets[preset_name].get("include", "")
            exc = self.custom_presets[preset_name].get("exclude", "")
        else:
            inc = presets.get(preset_name, {}).get("include", "")
            exc = presets.get(preset_name, {}).get("exclude", "")
        self.include_patterns.setText(inc)
        self.exclude_patterns.setText(exc)
        self.filter_enabled.setChecked(bool(inc or exc))

    def save_current_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name.strip():
            inc = self.include_patterns.text()
            exc = self.exclude_patterns.text()
            self.custom_presets[name.strip()] = {"include": inc, "exclude": exc}
            try:
                with open(self.presets_file, 'w') as f:
                    json.dump(self.custom_presets, f)
                self.preset_combo.addItem(name.strip())
                QMessageBox.information(self, "Success", f"Preset '{name}' saved.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save preset: {e}")

    def on_input_type_changed(self, text):
        if "Folder" in text:
            self.agg_input_path.setPlaceholderText("Select source folder...")
        else:
            self.agg_input_path.setPlaceholderText("Select ZIP archive...")

    def update_agg_output_extension(self):
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
            'exclude_patterns': self.exclude_patterns.text(),
            'token_counts': self.chk_token_count.isChecked()
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

    # ---------- Knowledge Graph methods ----------
    def on_graph_input_type_changed(self, text):
        if "Folder" in text:
            self.graph_input_path.setPlaceholderText("Select source folder...")
        else:
            self.graph_input_path.setPlaceholderText("Select ZIP archive...")

    def update_graph_output_extension(self):
        current = self.graph_output_path.text().strip()
        if not current:
            return
        fmt = self.graph_output_format.currentText()
        if "JSON-LD" in fmt:
            ext = ".jsonld"
        elif "GraphML" in fmt:
            ext = ".graphml"
        elif "HTML" in fmt:
            ext = ".html"
        else:
            ext = ""
        if ext:
            path = Path(current)
            new_path = path.with_suffix(ext)
            self.graph_output_path.setText(str(new_path))

    def browse_graph_input(self):
        if "Folder" in self.graph_input_type.currentText():
            folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
            if folder:
                self.graph_input_path.setText(folder)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, "Select ZIP File", "", "ZIP Files (*.zip)")
            if file_path:
                self.graph_input_path.setText(file_path)

    def browse_graph_output(self):
        fmt = self.graph_output_format.currentText()
        if "JSON-LD" in fmt:
            ext = ".jsonld"
            default = "knowledge_graph.jsonld"
        elif "GraphML" in fmt:
            ext = ".graphml"
            default = "knowledge_graph.graphml"
        elif "HTML" in fmt:
            ext = ".html"
            default = "knowledge_graph.html"
        else:
            ext = ""
            default = "knowledge_graph"
        path, _ = QFileDialog.getSaveFileName(self, "Save Knowledge Graph", default, f"*{ext}" if ext else "CSV files (*.csv)")
        if path:
            if ext and not path.endswith(ext):
                path += ext
            self.graph_output_path.setText(path)

    def log_graph(self, msg):
        self.graph_log.append(f"[{msg}]")
        self.graph_log.verticalScrollBar().setValue(self.graph_log.verticalScrollBar().maximum())

    def start_graph_build(self):
        in_path = self.graph_input_path.text().strip()
        out_path = self.graph_output_path.text().strip()
        if not in_path or not os.path.exists(in_path):
            self.log_graph("ERROR: Valid input required.")
            return
        if not out_path:
            self.log_graph("ERROR: Valid output path required.")
            return

        self.graph_process_btn.setEnabled(False)
        self.view_graph_btn.setEnabled(False)
        self.detect_cycles_btn.setEnabled(False)
        self.graph_process_btn.setText("BUILDING GRAPH...")
        self.graph_progress.setValue(0)
        self.graph_log.clear()

        options = {
            'extract_symbols': self.chk_extract_symbols.isChecked(),
            'extract_calls': self.chk_extract_calls.isChecked(),
            'extract_markdown': self.chk_extract_markdown.isChecked(),
            'extract_entities': self.chk_extract_entities.isChecked(),
            'extract_references': self.chk_extract_references.isChecked(),
            'extract_dir_hierarchy': self.chk_extract_dir_hierarchy.isChecked(),
            'max_nodes': self.graph_max_nodes.value(),
            'strength_threshold': self.graph_threshold.value(),
            'focus_file_types': [ext.strip() for ext in self.graph_focus_types.text().split(',') if ext.strip()],
            'output_format': self.graph_output_format.currentText(),
            'output_path': out_path
        }

        self.worker = GraphWorker(in_path, out_path, options)
        self.worker.progress.connect(self.update_graph_progress)
        self.worker.log.connect(self.log_graph)
        self.worker.finished.connect(self.graph_finished)
        self.worker.graph_data_ready.connect(self.store_graph_data)
        self.worker.cycles_detected.connect(self.display_cycles)
        self.worker.start()

    def update_graph_progress(self, val, msg):
        self.graph_progress.setValue(val)
        self.graph_status.setText(msg)

    def store_graph_data(self, nodes, edges):
        self.last_graph_data = (nodes, edges)
        self.last_graph_base = Path(self.graph_output_path.text().strip())
        self.view_graph_btn.setEnabled(True)
        self.detect_cycles_btn.setEnabled(True)

    def graph_finished(self, out_path, success):
        self.graph_process_btn.setEnabled(True)
        self.graph_process_btn.setText("BUILD KNOWLEDGE GRAPH")
        if success:
            self.graph_status.setText(f"Graph saved: {out_path}")
            self.log_graph(f"Knowledge graph successfully written to {out_path}")
        else:
            self.graph_status.setText("Graph building failed.")
            self.view_graph_btn.setEnabled(False)
            self.detect_cycles_btn.setEnabled(False)

    def display_cycles(self, cycles):
        if not cycles:
            QMessageBox.information(self, "Circular Dependencies", "No circular dependencies detected.")
            return
        msg = f"Found {len(cycles)} circular dependencies:\n\n"
        for i, cycle in enumerate(cycles[:20]):
            msg += f"{i+1}. {' → '.join(cycle)}\n"
        if len(cycles) > 20:
            msg += f"\n... and {len(cycles)-20} more."
        QMessageBox.information(self, "Circular Dependencies", msg)

    def open_embedded_viewer(self):
        if not self.last_graph_data:
            self.log_graph("No graph data available.")
            return
        nodes_dict, edges_list = self.last_graph_data
        if not nodes_dict or not edges_list:
            self.log_graph("Graph is empty.")
            return
        html_content = self.generate_graph_html(nodes_dict, edges_list)
        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle("Knowledge Graph Viewer")
        dialog.resize(1000, 800)
        layout = QVBoxLayout(dialog)
        web_view = QWebEngineView()
        web_view.setHtml(html_content)
        layout.addWidget(web_view)
        btn_save = QPushButton("Save as PNG")
        def save_png():
            pixmap = web_view.grab()
            file_path, _ = QFileDialog.getSaveFileName(dialog, "Save Graph as PNG", "graph_screenshot.png", "PNG Files (*.png)")
            if file_path:
                pixmap.save(file_path)
                QMessageBox.information(dialog, "Saved", f"Graph saved to {file_path}")
        btn_save.clicked.connect(save_png)
        layout.addWidget(btn_save)
        dialog.exec()

    def detect_cycles(self):
        if not self.last_graph_data:
            self.log_graph("No graph data. Build graph first.")
            return
        from workers import find_cycles_in_graph
        nodes, edges = self.last_graph_data
        cycles = find_cycles_in_graph(edges)
        self.display_cycles(cycles)

    def generate_graph_html(self, nodes_dict, edges_list):
        import json
        vis_nodes = []
        for nid, data in nodes_dict.items():
            display_name = data['name'][:30] + ('...' if len(data['name']) > 30 else '')
            color_map = {
                'directory': '#8B5CF6', 'file': '#3B82F6', 'function': '#10B981',
                'class': '#F59E0B', 'def': '#F59E0B', 'call': '#EF4444',
                'topic': '#EC4899', 'entity': '#06B6D4', 'heading': '#A855F7'
            }
            color = color_map.get(data['type'], '#6B7280')
            vis_nodes.append({
                'id': nid, 'label': display_name, 'title': f"Type: {data['type']}<br>Name: {data['name']}",
                'color': color, 'shape': 'dot' if data['type'] in ('function','call','topic','entity') else 'box',
                'group': data['type']
            })
        vis_edges = []
        for src, tgt, rel, w in edges_list:
            vis_edges.append({
                'from': src, 'to': tgt, 'label': rel, 'title': f"{rel} (weight: {w:.2f})",
                'arrows': 'to', 'color': {'color': '#888888'}
            })
        nodes_json = json.dumps(vis_nodes)
        edges_json = json.dumps(vis_edges)
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Knowledge Graph</title>
<script src="https://unpkg.com/vis-network@9.1.2/dist/vis-network.min.js"></script>
<style>body{{margin:0;padding:0;font-family:Segoe UI;background:#1e1e1e;color:#ccc;}} #mynetwork{{width:100%;height:90vh;border:none;}} .controls{{position:absolute;top:10px;right:10px;background:rgba(0,0,0,0.7);padding:8px;border-radius:5px;z-index:100;}} select{{margin-left:5px;}}</style>
</head>
<body>
<div class="controls">
    <label>Filter by type: </label>
    <select id="typeFilter">
        <option value="all">All</option>
        <option value="file">Files</option>
        <option value="directory">Directories</option>
        <option value="function,class,def">Functions/Classes</option>
        <option value="topic,entity">Topics/Entities</option>
    </select>
    <button onclick="resetView()">Reset</button>
</div>
<div id="mynetwork"></div>
<script>
    var nodes = new vis.DataSet({nodes_json});
    var edges = new vis.DataSet({edges_json});
    var container = document.getElementById('mynetwork');
    var data = {{nodes: nodes, edges: edges}};
    var options = {{
        nodes: {{size: 20, font: {{size: 12, color: '#fff'}}}},
        edges: {{smooth: true, font: {{size: 10, color: '#aaa'}}}},
        physics: {{enabled: true, stabilization: {{iterations: 100}}}},
        interaction: {{hover: true}}
    }};
    var network = new vis.Network(container, data, options);
    function resetView() {{ network.fit(); }}
    document.getElementById('typeFilter').addEventListener('change', function(e) {{
        var val = e.target.value;
        if (val === 'all') {{
            nodes.update({nodes_json});
        }} else {{
            var types = val.split(',');
            var filtered = {nodes_json}.filter(n => types.includes(n.group));
            nodes.clear();
            nodes.add(filtered);
        }}
    }});
</script>
</body></html>"""
        return html

    # ---------- Codebase Explainer methods ----------
    def browse_exp_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Codebase Folder")
        if folder:
            self.exp_input_path.setText(folder)

    def start_explanation(self):
        in_path = self.exp_input_path.text().strip()
        if not in_path or not os.path.isdir(in_path):
            QMessageBox.warning(self, "Error", "Please select a valid folder.")
            return
        self.exp_generate_btn.setEnabled(False)
        self.exp_generate_btn.setText("GENERATING...")
        self.exp_output.clear()
        options = {
            'include_arch': self.exp_include_arch.isChecked(),
            'include_entry': self.exp_include_entry.isChecked(),
            'include_dataflow': self.exp_include_dataflow.isChecked(),
            'max_files': self.exp_max_files.value()
        }
        self.worker = ExplainerWorker(in_path, options)
        self.worker.log.connect(lambda msg: self.exp_output.append(f"[INFO] {msg}"))
        self.worker.finished.connect(self.explanation_finished)
        self.worker.start()

    def explanation_finished(self, explanation, success):
        self.exp_generate_btn.setEnabled(True)
        self.exp_generate_btn.setText("GENERATE CODEBASE EXPLANATION")
        if success:
            self.exp_output.setText(explanation)
        else:
            self.exp_output.setText("Failed to generate explanation. See log for details.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())