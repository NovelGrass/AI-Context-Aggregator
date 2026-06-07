import os
import tempfile
import zipfile
import traceback
import re
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from extractors import extract_text, safe_extract_zip, should_skip_file
from conversation import reformat_conversation


class AggregatorWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, bool)
    log = pyqtSignal(str)

    def __init__(self, input_path, output_path, options):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.options = options
        self.temp_dir = None

    def sanitize_for_xml(self, text: str) -> str:
        """
        Removes control characters that are invalid in XML 1.0.
        Allowed: #x9, #xA, #xD, and #x20-#xD7FF, #xE000-#xFFFD, #x10000-#x10FFFF
        We'll replace any invalid char with a space or remove it.
        """
        # Remove ASCII control chars except tab, newline, carriage return
        # Also remove invalid Unicode surrogates 
        # This regex matches any character not allowed in XML 1.0
        invalid_xml_chars = re.compile(
            '[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]'
        )
        return invalid_xml_chars.sub(' ', text)  # replace with space

    def run(self):
        try:
            self.log.emit("Initializing aggregator...")
            if self.input_path.lower().endswith('.zip'):
                self.log.emit("Extracting ZIP (safe mode)...")
                self.temp_dir = tempfile.TemporaryDirectory()
                safe_extract_zip(self.input_path, self.temp_dir.name, self.log.emit)
                process_dir = self.temp_dir.name
            else:
                process_dir = self.input_path

            # Load .gitignore if requested
            ignore_spec = None
            gitignore = Path(process_dir) / '.gitignore'
            if self.options.get('respect_gitignore') and gitignore.exists():
                import pathspec
                with open(gitignore, 'r', encoding='utf-8', errors='replace') as f:
                    ignore_spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
                self.log.emit("Loaded .gitignore")

            skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', '.idea', '.vscode'}
            skip_exts = set()
            if self.options.get('skip_binaries'):
                skip_exts = {'.png','.jpg','.jpeg','.gif','.bmp','.ico','.exe','.dll','.so','.dylib',
                             '.bin','.zip','.tar','.gz','.7z','.mp4','.mp3','.avi','.mov','.mkv','.iso','.img'}

            include = []
            exclude = []
            if self.options.get('filters_enabled'):
                inc = self.options.get('include_patterns', '')
                if inc:
                    include = [p.strip() for p in inc.split(',') if p.strip()]
                exc = self.options.get('exclude_patterns', '')
                if exc:
                    exclude = [p.strip() for p in exc.split(',') if p.strip()]

            all_files = []
            for root, dirs, files in os.walk(process_dir):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for f in files:
                    fp = Path(root) / f
                    rel = fp.relative_to(process_dir)
                    rel_str = str(rel).replace('\\', '/')
                    if ignore_spec and ignore_spec.match_file(rel_str):
                        continue
                    if should_skip_file(fp, skip_exts, include, exclude):
                        continue
                    all_files.append((fp, rel_str))

            total = len(all_files)
            if total == 0:
                raise Exception("No files match the selected filters.")

            combined = []
            total_chars = 0
            fmt = self.options.get('output_format', 'txt')

            for idx, (fp, rel) in enumerate(all_files):
                self.progress.emit(int((idx+1)/total*100), f"Processing {fp.name}")
                text = extract_text(fp, self.log.emit)
                if text.strip():
                    # Clean surrogate pairs first
                    text = text.encode('utf-8', errors='replace').decode('utf-8')
                    # If output is XML, sanitize control chars
                    if fmt == 'xml':
                        text = self.sanitize_for_xml(text)
                    total_chars += len(text)
                    if fmt == 'md':
                        combined.append(f"\n## `{rel}`\n\n```\n{text.strip()}\n```\n")
                    elif fmt == 'xml':
                        # Also escape XML special characters? Not necessary if we keep CDATA? 
                        # But for safety, we'll wrap in CDATA if needed, or just assume text is clean.
                        # Better to use CDATA to avoid escaping issues.
                        combined.append(f'<FILE path="{rel}">\n<![CDATA[\n{text.strip()}\n]]>\n</FILE>\n')
                    else:  # plain text
                        combined.append(f"\n{'='*80}\nFILE: {rel}\n{'='*80}\n{text}\n")

            file_count = len(combined)
            token_estimate = total_chars // 4

            out_data = self.format_output(combined, file_count, total_chars, token_estimate, fmt)

            # Ensure output directory exists
            output_dir = Path(self.output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            if os.path.exists(self.output_path):
                os.remove(self.output_path)
                self.log.emit(f"Removed existing output file: {self.output_path}")

            with open(self.output_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(out_data)

            written_size = os.path.getsize(self.output_path)
            self.log.emit(f"Written file size: {written_size:,} bytes")

            self.finished.emit(self.output_path, True)
            self.log.emit(f"Aggregation complete. Files aggregated: {file_count} (out of {total} processed), "
                          f"Chars: {total_chars:,}, Tokens ~{token_estimate:,}")
        except Exception as e:
            self.log.emit(f"ERROR: {traceback.format_exc()}")
            self.finished.emit("", False)
        finally:
            if self.temp_dir:
                self.temp_dir.cleanup()

    def format_output(self, contents, file_count, total_chars, token_estimate, fmt):
        source = self.input_path
        if fmt == 'md':
            header = f"""# AI Context Aggregation

**Source:** `{source}`
**Files Processed:** {file_count}
**Total Characters:** {total_chars:,}
**Estimated Tokens:** {token_estimate:,}

---
"""
            return header + "\n".join(contents)
        elif fmt == 'xml':
            header = f"""<?xml version="1.0" encoding="UTF-8"?>
<AI_Context source="{source}" files="{file_count}" characters="{total_chars}" tokens_estimate="{token_estimate}">
"""
            footer = "\n</AI_Context>"
            return header + "\n".join(contents) + footer
        else:  # plain text
            header = f"""AI CONTEXT AGGREGATION
Source: {source}
Files Processed: {file_count}
Total Characters: {total_chars:,}
Estimated Tokens: {token_estimate:,}
{'='*80}

"""
            return header + "\n".join(contents)


class ConversationWorker(QThread):
    finished = pyqtSignal(str, bool)
    log = pyqtSignal(str)

    def __init__(self, input_file, output_file, output_format):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.output_format = output_format

    def run(self):
        try:
            self.log.emit(f"Reading conversation from: {self.input_file}")
            import chardet
            with open(self.input_file, 'rb') as f:
                raw_data = f.read()
                encoding = chardet.detect(raw_data)['encoding'] or 'utf-8'
            text = raw_data.decode(encoding, errors='replace')
            text = text.encode('utf-8', errors='replace').decode('utf-8')

            self.log.emit("Reformatting conversation for AI context...")
            formatted = reformat_conversation(text, self.output_format)

            output_dir = Path(self.output_file).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            with open(self.output_file, 'w', encoding='utf-8', errors='replace') as f:
                f.write(formatted)

            self.log.emit("Conversation reformatted successfully.")
            self.finished.emit(self.output_file, True)
        except Exception as e:
            self.log.emit(f"ERROR: {traceback.format_exc()}")
            self.finished.emit("", False)