import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("app/logs")

SECTION_RE = re.compile(r'^(\d+(?:\.\d+)*)\.?\s+([A-Z].*\S)$')
STEP_RE = re.compile(r'^(Step\s+\d+)\s*:?\s*(.*)$')
BOILERPLATE_RE = re.compile(r'(ACME Corporation\s*\||Confidential|Internal Use Only|Page\s+\d+)')



def chunk_id(collection_name, document):
    digest = hashlib.md5(f"{collection_name}:{document}".encode()).hexdigest()
    return f"{collection_name}-{digest}"


def _match_heading(line):
    step = STEP_RE.match(line)
    if step:
        title = step.group(2).strip()
        return f"{step.group(1)}: {title}".strip(": ").strip()
    section = SECTION_RE.match(line)
    if section:
        if len(line) > 60 or line.rstrip().endswith('.'):
            return None
        return f"{section.group(1)} {section.group(2)}".strip()
    return None


def parse_sections(page_texts, document_name):
    sections = []
    current = None
    pre = []

    def build(entry):
        return {
            "document": "\n".join(entry["body"]),
            "metadata": {
                "document_name": document_name,
                "page_number": entry["page_number"],
                "section_name": entry["section_name"],
                "line_number": entry["line_number"],
            },
        }

    for page_idx, text in enumerate(page_texts):
        if not text:
            continue
        page_number = page_idx + 1
        for line_idx, raw in enumerate(text.split("\n")):
            line = raw.strip()
            if not line or BOILERPLATE_RE.search(line):
                continue
            heading = _match_heading(line)
            if heading:
                if current is None and pre:
                    sections.append({
                        "document": "\n".join(pre),
                        "metadata": {
                            "document_name": document_name,
                            "page_number": 1,
                            "section_name": "Header",
                            "line_number": 1,
                        },
                    })
                    pre = []
                if current:
                    sections.append(build(current))
                current = {
                    "section_name": heading,
                    "page_number": page_number,
                    "line_number": line_idx + 1,
                    "body": [line],
                }
            elif current:
                current["body"].append(line)
            else:
                pre.append(line)

    if current:
        sections.append(build(current))
    return sections


def final_text(events):
    finals = [e["text"] for e in events if e["type"] == "final"]
    return finals[-1] if finals else ""


def format_trace(events):
    lines = ["\n────────── Agent Trace ──────────"]
    for event in events:
        etype = event["type"]
        if etype == "thought":
            lines.append(f"[thought] {event['text']}")
        elif etype == "tool_call":
            lines.append(f"[tool call] {event['name']}  input={json.dumps(event['input'])}")
        elif etype == "tool_result":
            lines.append(f"[tool result] {event['output']}")
        elif etype == "skill_used":
            lines.append(f"[skill] {event['name']}")
    lines.append("─────────────────────────────────")
    return "\n".join(lines)


def write_run_log(query, events, feedback):
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = LOG_DIR / f"query_{stamp}.json"
    record = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "events": events,
        "final": final_text(events),
        "feedback": feedback,
    }
    with open(path, "w") as f:
        json.dump(record, f, indent=2)


def record_feedback():
    choice = input("Was this helpful? [1] Helpful  [2] Not Helpful: ").strip()
    return "Helpful" if choice == "1" else "Not Helpful"
