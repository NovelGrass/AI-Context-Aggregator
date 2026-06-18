import os
import tempfile
import zipfile
import traceback
import re
from pathlib import Path
from collections import defaultdict

from PyQt6.QtCore import QThread, pyqtSignal

from extractors import extract_text, safe_extract_zip, should_skip_file
from conversation import reformat_conversation

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    import pathspec
except ImportError:
    pathspec = None


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
        invalid_xml_chars = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
        return invalid_xml_chars.sub(' ', text)

    def escape_cdata(self, text: str) -> str:
        return text.replace(']]>', ']]]]><![CDATA[>')

    def count_tokens(self, text: str) -> dict:
        if not TIKTOKEN_AVAILABLE or not self.options.get('token_counts', False):
            return {}
        counts = {}
        try:
            enc = tiktoken.encoding_for_model("gpt-4")
            counts['gpt4'] = len(enc.encode(text))
        except:
            counts['gpt4'] = 0
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            counts['claude'] = len(enc.encode(text))
        except:
            counts['claude'] = 0
        counts['gemini'] = len(text) // 4
        return counts

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

            ignore_spec = None
            gitignore = Path(process_dir) / '.gitignore'
            if self.options.get('respect_gitignore') and gitignore.exists() and pathspec:
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
            full_text = ""

            for idx, (fp, rel) in enumerate(all_files):
                self.progress.emit(int((idx+1)/total*100), f"Processing {fp.name}")
                text = extract_text(fp, self.log.emit)
                if text.strip():
                    text = text.encode('utf-8', errors='replace').decode('utf-8')
                    if fmt == 'xml':
                        text = self.sanitize_for_xml(text)
                    total_chars += len(text)
                    full_text += text + "\n\n"
                    if fmt == 'md':
                        combined.append(f"\n## `{rel}`\n\n```\n{text.strip()}\n```\n")
                    elif fmt == 'xml':
                        safe_text = self.escape_cdata(text.strip())
                        combined.append(f'<FILE path="{rel}">\n<![CDATA[\n{safe_text}\n]]>\n</FILE>\n')
                    else:
                        combined.append(f"\n{'='*80}\nFILE: {rel}\n{'='*80}\n{text}\n")

            file_count = len(combined)
            token_estimate = total_chars // 4

            # Handle token counts differently for XML
            token_counts = None
            if self.options.get('token_counts', False) and TIKTOKEN_AVAILABLE:
                token_counts = self.count_tokens(full_text)

            out_data = self.format_output(combined, file_count, total_chars, token_estimate, fmt, token_counts)

            output_dir = Path(self.output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            if os.path.exists(self.output_path):
                os.remove(self.output_path)
            # Write without trailing whitespace
            with open(self.output_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(out_data.strip())

            self.log.emit(f"Written file size: {os.path.getsize(self.output_path):,} bytes")
            self.finished.emit(self.output_path, True)
            self.log.emit(f"Aggregation complete. Files: {file_count}, Chars: {total_chars:,}, Tokens ~{token_estimate:,}")
        except Exception as e:
            self.log.emit(f"ERROR: {traceback.format_exc()}")
            self.finished.emit("", False)
        finally:
            if self.temp_dir:
                self.temp_dir.cleanup()

    def format_output(self, contents, file_count, total_chars, token_estimate, fmt, token_counts=None):
        source = self.input_path
        if fmt == 'md':
            header = f"""# AI Context Aggregation

**Source:** `{source}`
**Files Processed:** {file_count}
**Total Characters:** {total_chars:,}
**Estimated Tokens (4 chars ≈ 1 token):** {token_estimate:,}

---
"""
            output = header + "\n".join(contents)
            if token_counts:
                token_section = f"\n\n## Token Counts (Approximate)\n- GPT-4: {token_counts.get('gpt4', 0)} tokens\n- Claude: {token_counts.get('claude', 0)} tokens\n- Gemini: {token_counts.get('gemini', 0)} tokens\n"
                output += token_section
            return output
        elif fmt == 'xml':
            header = f"""<?xml version="1.0" encoding="UTF-8"?>
<AI_Context source="{source}" files="{file_count}" characters="{total_chars}" tokens_estimate="{token_estimate}">
"""
            footer = "\n</AI_Context>"
            body = "\n".join(contents)
            # Insert token counts as an element if available
            if token_counts:
                token_elem = f'\n  <token_counts gpt4="{token_counts.get("gpt4",0)}" claude="{token_counts.get("claude",0)}" gemini="{token_counts.get("gemini",0)}"/>\n'
                # Insert before footer
                output = header + body + token_elem + footer
            else:
                output = header + body + footer
            return output
        else:  # plain text
            header = f"""AI CONTEXT AGGREGATION
Source: {source}
Files Processed: {file_count}
Total Characters: {total_chars:,}
Estimated Tokens (4 chars = 1 token): {token_estimate:,}
{'='*80}

"""
            output = header + "\n".join(contents)
            if token_counts:
                token_section = f"\n\nToken Counts (Approximate):\nGPT-4: {token_counts.get('gpt4', 0)} tokens\nClaude: {token_counts.get('claude', 0)} tokens\nGemini: {token_counts.get('gemini', 0)} tokens\n"
                output += token_section
            return output


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
            self.log.emit("Reformatting conversation...")
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


def find_cycles_in_graph(edges):
    graph = defaultdict(list)
    for src, tgt, rel, w in edges:
        graph[src].append(tgt)
    cycles = []
    def dfs(node, visited, path):
        visited[node] = 1
        path.append(node)
        for nei in graph[node]:
            if visited.get(nei) == 1:
                idx = path.index(nei)
                cycles.append(path[idx:] + [nei])
            elif visited.get(nei) == 0:
                dfs(nei, visited, path)
        visited[node] = 2
        path.pop()
    for node in graph:
        visited = {n:0 for n in graph}
        dfs(node, visited, [])
    unique = []
    for c in cycles:
        c_set = set(c)
        if not any(c_set == set(uc) for uc in unique):
            unique.append(c)
    return unique[:20]


class GraphWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, bool)
    log = pyqtSignal(str)
    graph_data_ready = pyqtSignal(dict, list)
    cycles_detected = pyqtSignal(list)

    def __init__(self, input_path, output_path, options):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.options = options
        self.temp_dir = None

    def extract_noun_phrases(self, text):
        pattern = r'\b(?:[A-Z][a-z]*\s+){1,3}[A-Z][a-z]*\b'
        matches = re.findall(pattern, text)
        acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
        return list(set(matches + acronyms))

    def extract_entities(self, text):
        entities = []
        persons = re.findall(r'(?:Mr\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', text)
        entities.extend(persons)
        orgs = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Inc\.|Corp\.|LLC|University|Institute|School))\b', text)
        entities.extend(orgs)
        indicators = r'(?:Company|Corporation|Organization|Foundation|Agency|Department|Ministry)'
        orgs2 = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+' + indicators, text)
        entities.extend(orgs2)
        return list(set(entities))

    def extract_function_calls(self, text, language):
        calls = []
        keywords = {'if','for','while','switch','return','assert','pass','break','continue','elif','else'}
        if language in ('python', 'js', 'ts', 'java', 'c', 'cpp', 'go', 'rs'):
            matches = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', text)
            calls = [m for m in matches if m not in keywords]
        return list(set(calls))

    def extract_definitions(self, text, language):
        definitions = {}
        if language == 'python':
            for m in re.finditer(r'^(def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)', text, re.MULTILINE):
                definitions[m.group(2)] = m.group(1)
        elif language in ('js', 'ts'):
            for m in re.finditer(r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', text):
                definitions[m.group(1)] = 'function'
            for m in re.finditer(r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)', text):
                definitions[m.group(1)] = 'class'
        elif language in ('c', 'cpp', 'java'):
            for m in re.finditer(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{', text):
                if m.group(1) not in ('if','for','while','switch'):
                    definitions[m.group(1)] = 'function'
            for m in re.finditer(r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)', text):
                definitions[m.group(1)] = 'class'
        return definitions

    def extract_imports(self, text, language):
        imports = []
        if language == 'python':
            imports += re.findall(r'^\s*import\s+([a-zA-Z_][a-zA-Z0-9_.]*)', text, re.MULTILINE)
            imports += re.findall(r'^\s*from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import', text, re.MULTILINE)
        elif language in ('js', 'ts'):
            imports += re.findall(r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', text)
            imports += re.findall(r'require\([\'"]([^\'"]+)[\'"]\)', text)
        elif language in ('c', 'cpp'):
            imports += re.findall(r'#include\s*[<"]([^>"]+)[>"]', text)
        return list(set(imports))

    def resolve_import_to_file(self, imp, all_files, current_file_rel):
        imp = imp.replace('\\', '/')
        if imp.startswith('./'):
            imp = imp[2:]
        candidates = []
        if '.' in imp:
            path_py = imp.replace('.', '/') + '.py'
            candidates.append(path_py)
            init_py = imp.replace('.', '/') + '/__init__.py'
            candidates.append(init_py)
        else:
            candidates.append(imp + '.py')
            candidates.append(imp + '/__init__.py')
        candidates.append(imp)
        candidates += [imp + '.js', imp + '.ts']
        for cand in candidates:
            for fp, rel in all_files:
                if rel == cand or rel.endswith('/' + cand):
                    return rel
        base = imp.split('/')[-1].split('.')[0]
        for fp, rel in all_files:
            if Path(rel).stem == base:
                return rel
        return None

    def run(self):
        try:
            self.log.emit("Starting advanced knowledge graph builder...")
            if self.input_path.lower().endswith('.zip'):
                self.log.emit("Extracting ZIP archive...")
                self.temp_dir = tempfile.TemporaryDirectory()
                safe_extract_zip(self.input_path, self.temp_dir.name, self.log.emit)
                root_dir = Path(self.temp_dir.name)
            else:
                root_dir = Path(self.input_path)

            focus = self.options.get('focus_file_types', [])
            all_files = []
            skip_exts = {'.png','.jpg','.jpeg','.gif','.bmp','.ico','.exe','.dll','.so','.dylib',
                         '.bin','.zip','.tar','.gz','.7z','.mp4','.mp3','.avi','.mov','.mkv','.iso','.img'}
            for fp in root_dir.rglob('*'):
                if fp.is_file() and fp.suffix.lower() not in skip_exts and fp.stat().st_size < 10*1024*1024:
                    if focus and fp.suffix.lower() not in focus:
                        continue
                    rel = fp.relative_to(root_dir)
                    all_files.append((fp, str(rel)))

            total = len(all_files)
            if total == 0:
                raise Exception("No matching files found.")

            nodes = {}
            edges = []
            edge_weights = defaultdict(float)
            file_definitions = {}
            file_calls = {}

            def add_node(node_id, node_type, name, metadata=None):
                if node_id not in nodes:
                    nodes[node_id] = {'type': node_type, 'name': name, 'metadata': metadata or {}}

            def add_edge(src, tgt, rel_type, weight=1.0):
                if src == tgt:
                    return
                key = (src, tgt, rel_type)
                edge_weights[key] += weight

            code_exts = {'.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php'}
            self.log.emit("First pass: scanning code files...")
            for fp, rel in all_files:
                ext = fp.suffix.lower()
                if ext in code_exts:
                    try:
                        text = extract_text(fp, self.log.emit)
                        lang = 'python' if ext == '.py' else ('js' if ext in ('.js','.ts') else 'c' if ext in ('.c','.cpp','.h','.hpp') else 'generic')
                        defs = self.extract_definitions(text, lang)
                        file_definitions[rel] = defs
                        if self.options.get('extract_calls', True):
                            calls = self.extract_function_calls(text, lang)
                            file_calls[rel] = set(calls)
                    except Exception as e:
                        self.log.emit(f"Warning: parse error {rel}: {str(e)}")

            self.progress.emit(10, "Building graph...")

            if self.options.get('extract_dir_hierarchy', True):
                self.log.emit("Building directory hierarchy...")
                for fp, rel in all_files:
                    parts = Path(rel).parts
                    parent = ""
                    for i, part in enumerate(parts[:-1]):
                        cur = str(Path(*parts[:i+1]))
                        add_node(cur, "directory", part, {'full_path': cur})
                        if parent:
                            add_edge(parent, cur, "contains")
                        parent = cur
                    file_id = rel
                    add_node(file_id, "file", fp.name, {'path': rel, 'size': fp.stat().st_size})
                    if parent:
                        add_edge(parent, file_id, "contains")

            if self.options.get('extract_symbols', True):
                self.log.emit("Adding code symbols...")
                for rel, defs in file_definitions.items():
                    for sym_name, sym_type in defs.items():
                        sym_id = f"{rel}::{sym_name}"
                        add_node(sym_id, sym_type, sym_name, {'file': rel})
                        add_edge(rel, sym_id, "defines")

            if self.options.get('extract_calls', True):
                self.log.emit("Resolving cross-file calls...")
                symbol_to_files = defaultdict(list)
                for rel, defs in file_definitions.items():
                    for sym_name in defs.keys():
                        symbol_to_files[sym_name].append(rel)
                for src_file, calls in file_calls.items():
                    for call in calls:
                        target_files = symbol_to_files.get(call, [])
                        for tgt_file in target_files:
                            if tgt_file != src_file:
                                add_edge(src_file, tgt_file, "calls", weight=1.0)
                            sym_id = f"{tgt_file}::{call}"
                            if sym_id in nodes:
                                add_edge(src_file, sym_id, "calls")

            if self.options.get('extract_references', True):
                self.log.emit("Resolving imports...")
                for fp, rel in all_files:
                    ext = fp.suffix.lower()
                    lang = None
                    if ext == '.py':
                        lang = 'python'
                    elif ext in ('.js', '.ts'):
                        lang = 'js'
                    elif ext in ('.c', '.cpp', '.h', '.hpp'):
                        lang = 'c'
                    if lang:
                        try:
                            text = extract_text(fp, self.log.emit)
                            imports = self.extract_imports(text, lang)
                            for imp in imports:
                                target_rel = self.resolve_import_to_file(imp, all_files, rel)
                                if target_rel and target_rel != rel:
                                    add_edge(rel, target_rel, "imports", weight=1.0)
                        except Exception as e:
                            self.log.emit(f"Warning: import resolution failed for {rel}: {str(e)}")

            if self.options.get('extract_markdown', True):
                self.log.emit("Extracting topics...")
                for fp, rel in all_files:
                    if fp.suffix.lower() in ('.md', '.txt', '.rst'):
                        try:
                            text = extract_text(fp, self.log.emit)
                            phrases = self.extract_noun_phrases(text)
                            for phrase in phrases:
                                phrase_id = f"topic::{phrase}"
                                add_node(phrase_id, "topic", phrase)
                                add_edge(rel, phrase_id, "mentions")
                        except:
                            pass

            if self.options.get('extract_entities', True):
                self.log.emit("Extracting named entities...")
                for fp, rel in all_files:
                    if fp.suffix.lower() in ('.pdf', '.docx'):
                        try:
                            text = extract_text(fp, self.log.emit)
                            entities = self.extract_entities(text)
                            for ent in entities:
                                ent_id = f"entity::{ent}"
                                add_node(ent_id, "entity", ent)
                                add_edge(rel, ent_id, "contains_entity")
                        except:
                            pass

            all_edges = [(src, tgt, rel, w) for (src, tgt, rel), w in edge_weights.items()]
            threshold = self.options.get('strength_threshold', 0.1)
            all_edges = [(s,t,r,w) for (s,t,r,w) in all_edges if w >= threshold]

            max_nodes = self.options.get('max_nodes', 500)
            if len(nodes) > max_nodes:
                node_degree = defaultdict(float)
                for src, tgt, rel, w in all_edges:
                    node_degree[src] += w
                    node_degree[tgt] += w
                sorted_nodes = sorted(node_degree.items(), key=lambda x: x[1], reverse=True)
                keep_ids = {nid for nid, _ in sorted_nodes[:max_nodes]}
                for nid in list(nodes.keys()):
                    if nid not in keep_ids and nodes[nid]['type'] != 'directory':
                        del nodes[nid]
                all_edges = [(s,t,r,w) for (s,t,r,w) in all_edges if s in nodes and t in nodes]

            cycles = find_cycles_in_graph(all_edges)
            if cycles:
                self.cycles_detected.emit(cycles)

            self.graph_data_ready.emit(nodes, all_edges)

            self.progress.emit(90, "Writing graph file...")
            out_format = self.options.get('output_format', 'JSON-LD (schema.org)')
            output_base = Path(self.output_path)
            if "JSON-LD" in out_format:
                out_data = self.format_jsonld(nodes, all_edges)
                output_base = output_base.with_suffix('.jsonld')
                with open(output_base, 'w', encoding='utf-8') as f:
                    f.write(out_data)
            elif "GraphML" in out_format:
                out_data = self.format_graphml(nodes, all_edges)
                output_base = output_base.with_suffix('.graphml')
                with open(output_base, 'w', encoding='utf-8') as f:
                    f.write(out_data)
            elif "HTML" in out_format:
                html_content = self.generate_html_view(nodes, all_edges)
                output_base = output_base.with_suffix('.html')
                with open(output_base, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            else:
                nodes_csv = output_base.parent / (output_base.stem + "_nodes.csv")
                edges_csv = output_base.parent / (output_base.stem + "_edges.csv")
                self.write_csv(nodes, all_edges, nodes_csv, edges_csv)
                output_base = nodes_csv

            self.progress.emit(100, "Done!")
            self.log.emit(f"Graph built: {len(nodes)} nodes, {len(all_edges)} edges")
            self.finished.emit(str(output_base), True)

        except Exception as e:
            self.log.emit(f"ERROR: {traceback.format_exc()}")
            self.finished.emit("", False)
        finally:
            if self.temp_dir:
                self.temp_dir.cleanup()

    def format_jsonld(self, nodes, edges):
        import json
        context = {"@context": {"schema": "http://schema.org/", "type": "@type", "name": "schema:name", "id": "@id"}}
        graph = []
        for nid, data in nodes.items():
            node = {"@id": nid, "@type": data['type'].capitalize(), "name": data['name']}
            if 'metadata' in data and data['metadata']:
                node.update(data['metadata'])
            graph.append(node)
        for src, tgt, rel, w in edges:
            edge = {"@id": f"{src}->{tgt}", "@type": "Relationship", "source": src, "target": tgt, "relationType": rel, "weight": w}
            graph.append(edge)
        return json.dumps({"@context": context["@context"], "@graph": graph}, indent=2)

    def format_graphml(self, nodes, edges):
        import xml.etree.ElementTree as ET
        from xml.dom import minidom
        graphml = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
        graph = ET.SubElement(graphml, "graph", id="G", edgedefault="directed")
        ET.SubElement(graphml, "key", id="type", for_="node", attr_name="type")
        ET.SubElement(graphml, "key", id="name", for_="node", attr_name="name")
        ET.SubElement(graphml, "key", id="weight", for_="edge", attr_name="weight")
        ET.SubElement(graphml, "key", id="relation", for_="edge", attr_name="type")
        for nid, data in nodes.items():
            node = ET.SubElement(graph, "node", id=nid)
            ET.SubElement(node, "data", key="type").text = data['type']
            ET.SubElement(node, "data", key="name").text = data['name']
        for src, tgt, rel, w in edges:
            edge = ET.SubElement(graph, "edge", source=src, target=tgt)
            ET.SubElement(edge, "data", key="weight").text = str(w)
            ET.SubElement(edge, "data", key="relation").text = rel
        rough = ET.tostring(graphml, 'utf-8')
        parsed = minidom.parseString(rough)
        return parsed.toprettyxml(indent="  ")

    def write_csv(self, nodes, edges, nodes_path, edges_path):
        import csv
        with open(nodes_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'type', 'name', 'metadata'])
            for nid, data in nodes.items():
                writer.writerow([nid, data['type'], data['name'], str(data.get('metadata', {}))])
        with open(edges_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['source', 'target', 'relation_type', 'weight'])
            for src, tgt, rel, w in edges:
                writer.writerow([src, tgt, rel, w])

    def generate_html_view(self, nodes, edges):
        import json
        vis_nodes = []
        for nid, data in nodes.items():
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
        for src, tgt, rel, w in edges:
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


class ExplainerWorker(QThread):
    finished = pyqtSignal(str, bool)
    log = pyqtSignal(str)

    def __init__(self, folder_path, options):
        super().__init__()
        self.folder_path = folder_path
        self.options = options

    def run(self):
        try:
            self.log.emit("Analyzing codebase...")
            root = Path(self.folder_path)
            code_exts = {'.py','.js','.ts','.java','.c','.cpp','.h','.hpp','.cs','.go','.rs','.rb','.php','.md','.txt'}
            files = []
            for ext in code_exts:
                files.extend(root.rglob(f"*{ext}"))
            files = files[:self.options.get('max_files', 50)]
            self.log.emit(f"Analyzing {len(files)} files...")

            imports = defaultdict(list)
            entry_points = []
            for fp in files:
                rel = fp.relative_to(root)
                try:
                    text = extract_text(fp, self.log.emit)
                    for line in text.splitlines():
                        if line.strip().startswith(('import ', 'from ')):
                            imports[str(rel)].append(line.strip())
                except:
                    pass
                if fp.stem in ('main', 'app', 'index', 'server', 'cli', 'run'):
                    entry_points.append(str(rel))

            explanation = f"# Codebase Explanation: {root.name}\n\n"
            explanation += f"## Overview\n- Total files analyzed: {len(files)}\n- Main languages: {', '.join(set(fp.suffix for fp in files))}\n\n"
            if entry_points:
                explanation += f"## Entry Points\nLikely entry files: {', '.join(entry_points)}\n\n"
            if imports:
                explanation += "## Dependency Highlights\n"
                for file, imp_list in list(imports.items())[:20]:
                    explanation += f"- `{file}` imports: {imp_list[0]}\n"
            explanation += "\n## Architecture Summary\n"
            explanation += "This codebase appears to be structured as follows:\n"
            dirs = set()
            for fp in files:
                dirs.add(fp.parent.relative_to(root))
            explanation += f"- Top-level directories: {', '.join(str(d) for d in dirs if str(d) != '.')}\n"
            explanation += "\n## Next Steps for LLM\n"
            explanation += "Based on this analysis, you can now ask specific questions about module dependencies, entry points, or request refactoring advice."
            self.finished.emit(explanation, True)
        except Exception as e:
            self.log.emit(f"Error: {str(e)}")
            self.finished.emit("", False)