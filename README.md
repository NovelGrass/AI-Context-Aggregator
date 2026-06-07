# AI Context Aggregator

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Aggregate entire folders, codebases, or conversations into a single AI‑optimised context file.**

Supports **10+ file formats** (PDF, DOCX, XLSX, PPTX, source code, logs) and produces **clean Markdown, Plain Text, or XML‑tagged** output ready for LLMs like Claude, ChatGPT, Gemini, or local models.

---

## Features

- 📁 **Folder or ZIP input** — Recursively process directories or uploaded ZIP archives.
- 🔒 **Safe ZIP extraction** – prevents zip‑slip attacks.
- 📄 **Rich file support** – PDF, DOCX, XLSX, PPTX, TXT, MD, PY, and many more.
- 🎯 **Smart filtering** – include/exclude by glob patterns, respect `.gitignore`, skip binaries.
- 🌐 **Encoding detection** – automatically handles UTF-8, ISO‑8859‑1, etc.
- 📊 **Output statistics** – file count, characters, estimated tokens (4 chars ≈ 1 token).
- 💬 **Conversation reformatter** – turns raw chat logs (User/Assistant) into structured AI context.
- 🎨 **Polished UI** – dark theme, clean and professional.
- 🚀 **PyInstaller ready** – build a standalone `.exe` or macOS app.

---

## Installation

### From source

```bash
git clone https://github.com/yourusername/AI-Context-Aggregator.git
cd AI-Context-Aggregator
pip install -r requirements.txt
python main.py