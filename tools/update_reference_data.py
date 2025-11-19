#!/usr/bin/env python3
"""Generate JSON reference data for the Tk yank maker UI."""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
CONFIG_DOC = DOCS_DIR / "configuration.md"
PRECONFIG_DOC = DOCS_DIR / "preconfigured-pages.md"
OUTPUT_PATH = DOCS_DIR / "reference_data.json"
GO_YAML_HELPER = REPO_ROOT / "tools" / "yaml_to_json.go"


def extract_widgets() -> List[Dict[str, Any]]:
    if not CONFIG_DOC.exists():
        return []
    text = CONFIG_DOC.read_text(encoding="utf-8")
    try:
        start = text.index("## Widgets")
    except ValueError:
        return []
    try:
        end = text.index("\n## ", start + len("## Widgets"))
    except ValueError:
        end = len(text)
    widget_text = text[start:end]
    section_re = re.compile(r"^###\s+(?P<name>.+?)\n(?P<body>.*?)(?=^###\s+|\Z)", re.S | re.M)
    type_re = re.compile(r"-\s+type:\s*([A-Za-z0-9_-]+)")
    widgets: List[Dict[str, Any]] = []
    for match in section_re.finditer(widget_text):
        body = textwrap.dedent(match.group("body")).strip()
        type_match = type_re.search(body)
        if not type_match:
            continue
        widget_type = type_match.group(1).strip()
        widget_entry: Dict[str, Any] = {
            "name": match.group("name").strip(),
            "type": widget_type,
            "markdown": body,
        }
        example = extract_example_widget(body, widget_type)
        if example is not None:
            widget_entry["example"] = example
        widgets.append(widget_entry)

    seen: Dict[str, Dict[str, Any]] = {}
    for widget in widgets:
        widget_type = widget.get("type")
        if not widget_type:
            continue
        seen.setdefault(widget_type, widget)
    return sorted(seen.values(), key=lambda item: item.get("type", ""))


def extract_templates() -> List[Dict[str, Any]]:
    if not PRECONFIG_DOC.exists():
        return []
    text = PRECONFIG_DOC.read_text(encoding="utf-8")
    section_re = re.compile(r"^##\s+(?P<name>.+?)\n(?P<body>.*?)(?=^##\s+|\Z)", re.S | re.M)
    image_re = re.compile(r"!\[[^\]]*\]\((?P<path>[^)]+)\)")
    require_re = re.compile(r"requires\s+Glance\s+<code>([^<]+)</code>", re.I)
    yaml_re = re.compile(r"```yaml(.*?)```", re.S)
    templates: List[Dict[str, Any]] = []
    for match in section_re.finditer(text):
        body = match.group("body")
        yaml_match = yaml_re.search(body)
        if not yaml_match:
            continue
        name = match.group("name").strip()
        yaml_text = textwrap.dedent(yaml_match.group(1)).strip("\n")
        image_match = image_re.search(body)
        require_match = require_re.search(body)
        templates.append(
            {
                "name": name,
                "preview_image": image_match.group("path") if image_match else None,
                "requires": require_match.group(1).strip() if require_match else None,
                "yaml": yaml_text,
            }
        )
    return templates


def extract_example_widget(body: str, expected_type: str) -> Optional[Dict[str, Any]]:
    code_match = re.search(r"```(?:yaml|yml)(.*?)```", body, re.S | re.I)
    if not code_match:
        return None
    snippet = textwrap.dedent(code_match.group(1)).strip()
    if not snippet:
        return None
    parsed = parse_yaml_snippet(snippet)
    if parsed is None:
        return None
    return find_widget_with_type(parsed, expected_type)


def parse_yaml_snippet(snippet: str) -> Optional[Any]:
    if not GO_YAML_HELPER.exists():
        return None
    try:
        result = subprocess.run(
            ["go", "run", str(GO_YAML_HELPER)],
            input=snippet,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def find_widget_with_type(node: Any, expected_type: str) -> Optional[Dict[str, Any]]:
    if isinstance(node, dict):
        node_type = node.get("type")
        if isinstance(node_type, str) and node_type.strip() == expected_type:
            return node
        for value in node.values():
            match = find_widget_with_type(value, expected_type)
            if match is not None:
                return match
    elif isinstance(node, list):
        for item in node:
            match = find_widget_with_type(item, expected_type)
            if match is not None:
                return match
    return None


def main() -> None:
    data = {"widgets": extract_widgets(), "templates": extract_templates()}
    OUTPUT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} with {len(data['widgets'])} widgets and {len(data['templates'])} templates.")


if __name__ == "__main__":
    main()
