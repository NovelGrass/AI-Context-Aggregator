import re
import html

def escape_xml(text: str) -> str:
    return html.escape(text)

def reformat_conversation(raw_text: str, output_format: str = 'md') -> str:
    """
    Convert raw conversation into structured AI context.
    Supports 'md' (Markdown), 'txt' (plain), and 'xml' (LLM‑optimised).
    """
    lines = raw_text.splitlines()
    processed = []
    current_role = None
    current_content = []

    role_patterns = {
        'user': r'^(User|Human|You|Customer|H):\s*',
        'assistant': r'^(Assistant|AI|ChatGPT|Gemini|Meta|Claude|Bot|A):\s*'
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        matched = False
        for role, pattern in role_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                if current_role and current_content:
                    content = ' '.join(current_content).strip()
                    if content:
                        processed.append((current_role, content))
                current_role = role
                current_content = [line[match.end():]]
                matched = True
                break

        if not matched:
            if current_role:
                current_content.append(line)
            else:
                current_role = 'user'
                current_content.append(line)

    if current_role and current_content:
        content = ' '.join(current_content).strip()
        if content:
            processed.append((current_role, content))

    if not processed:
        if output_format == 'md':
            return f"## Conversation Transcript\n\n{raw_text}"
        elif output_format == 'xml':
            return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<conversation>\n{escape_xml(raw_text)}\n</conversation>"
        else:
            return f"Conversation Transcript\n{'='*40}\n{raw_text}"

    if output_format == 'md':
        formatted = []
        for role, content in processed:
            label = "USER" if role == 'user' else "ASSISTANT"
            formatted.append(f"**{label}:** {content}\n")
        return "\n---\n".join(formatted)

    elif output_format == 'xml':
        formatted = []
        for role, content in processed:
            tag = "user" if role == 'user' else "assistant"
            escaped_content = escape_xml(content)
            formatted.append(f"<{tag}>{escaped_content}</{tag}>")
        # Wrap with root element and add XML declaration
        return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<conversation>\n" + "\n".join(formatted) + "\n</conversation>"

    else:  # plain text
        formatted = []
        for role, content in processed:
            label = "USER" if role == 'user' else "ASSISTANT"
            formatted.append(f"{label}: {content}\n")
        return "\n" + "-"*40 + "\n".join(formatted)