#!/usr/bin/env python3
"""Tkinter helper that builds Glance YAML configurations.

The UI mirrors the hierarchy described in the documentation under
`docs/configuration.md`, making it easier to translate Pages -> Columns -> Widgets
into a YAML document.
"""
from __future__ import annotations

import json
import re
import tkinter as tk
from collections import OrderedDict
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional, Tuple

try:  # Optional dependency for loading existing YAML files.
    import yaml
except ImportError:  # pragma: no cover - Tkinter tool
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
CONFIG_DOC = DOCS_DIR / "configuration.md"
SAMPLE_CONFIG = DOCS_DIR / "glance.yml"
REFERENCE_DATA_FILE = DOCS_DIR / "reference_data.json"


def _load_reference_data() -> Dict[str, Any]:
    if not REFERENCE_DATA_FILE.exists():
        return {"widgets": [], "templates": []}
    try:
        data = json.loads(REFERENCE_DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"widgets": [], "templates": []}
    if not isinstance(data, dict):
        return {"widgets": [], "templates": []}
    widgets = data.get("widgets")
    templates = data.get("templates")
    return {
        "widgets": list(widgets) if isinstance(widgets, list) else [],
        "templates": list(templates) if isinstance(templates, list) else [],
    }


REFERENCE_DATA = _load_reference_data()
RAW_WIDGETS = REFERENCE_DATA.get("widgets", [])
if RAW_WIDGETS and isinstance(RAW_WIDGETS, list) and RAW_WIDGETS and isinstance(RAW_WIDGETS[0], dict):
    WIDGETS_DATA = [widget for widget in RAW_WIDGETS if isinstance(widget, dict)]
    WIDGET_TYPES = [widget.get("type", "") for widget in WIDGETS_DATA if isinstance(widget.get("type"), str)]
else:
    WIDGETS_DATA = []
    WIDGET_TYPES = [widget for widget in RAW_WIDGETS if isinstance(widget, str)]
WIDGET_TYPES = sorted(dict.fromkeys(filter(None, WIDGET_TYPES)))
WIDGET_DOC_MAP = {widget.get("type"): widget for widget in WIDGETS_DATA if isinstance(widget.get("type"), str)}
TEMPLATES = REFERENCE_DATA.get("templates", [])


# ---------------------------------------------------------------------------
# Structure helpers
# ---------------------------------------------------------------------------


def _ordered_copy(value: Any) -> Any:
    """Recursively convert mappings to OrderedDict instances."""

    if isinstance(value, dict):
        return OrderedDict((key, _ordered_copy(val)) for key, val in value.items())
    if isinstance(value, list):
        return [_ordered_copy(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _quote_scalar(value: str) -> str:
    """Return a safely quoted scalar for YAML output."""
    if value == "":
        return "''"
    if re.search(r"[:#\-\[\]\{\}\n]|^\s|\s$", value):
        return json.dumps(value)
    return value


def format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return _quote_scalar(str(value))


def to_yaml(value: Any, indent: int = 0) -> str:
    space = "  " * indent
    if isinstance(value, dict):
        if not value:
            return f"{space}{{}}"
        lines: List[str] = []
        for key, val in value.items():
            key_str = _quote_scalar(str(key))
            if isinstance(val, (dict, list)):
                lines.append(f"{space}{key_str}:")
                lines.append(to_yaml(val, indent + 1))
            else:
                lines.append(f"{space}{key_str}: {format_scalar(val)}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{space}[]"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 1))
            else:
                lines.append(f"{space}- {format_scalar(item)}")
        return "\n".join(lines)
    return f"{space}{format_scalar(value)}"


# ---------------------------------------------------------------------------
# Data manipulation helpers
# ---------------------------------------------------------------------------


class ValueDialog(simpledialog.Dialog):
    """Modal dialog that captures a scalar/list/dict value (and optional key)."""

    TYPE_CHOICES = [
        ("Text", "string"),
        ("Integer", "integer"),
        ("Float", "float"),
        ("Boolean", "boolean"),
        ("Null", "null"),
        ("Dictionary", "dict"),
        ("List", "list"),
    ]
    LABEL_TO_VALUE = {label: value for label, value in TYPE_CHOICES}
    VALUE_TO_LABEL = {value: label for label, value in TYPE_CHOICES}

    def __init__(
        self,
        master: tk.Widget,
        title: str,
        allow_key_edit: bool = False,
        initial_key: str = "",
        initial_value: Any = "",
    ) -> None:
        self.allow_key_edit = allow_key_edit
        self.initial_key = initial_key
        self.initial_value = initial_value
        self.result_data: Optional[Tuple[Optional[str], Any]] = None
        super().__init__(master, title)

    def body(self, master: tk.Widget) -> tk.Widget:
        row = 0
        if self.allow_key_edit:
            ttk.Label(master, text="Key").grid(row=row, column=0, sticky="w", padx=6, pady=(6, 2))
            self.key_var = tk.StringVar(value=self.initial_key)
            self.key_entry = ttk.Entry(master, textvariable=self.key_var, width=32)
            self.key_entry.grid(row=row + 1, column=0, sticky="we", padx=6)
            row += 2
        else:
            self.key_var = tk.StringVar(value="")
            self.key_entry = None

        ttk.Label(master, text="Value type").grid(row=row, column=0, sticky="w", padx=6, pady=(6, 2))
        self.type_var = tk.StringVar()
        type_combo = ttk.Combobox(
            master,
            textvariable=self.type_var,
            state="readonly",
            values=[label for label, _ in self.TYPE_CHOICES],
        )
        type_combo.grid(row=row + 1, column=0, sticky="we", padx=6)

        row += 2
        ttk.Label(master, text="Value (leave empty for dict/list/null)").grid(
            row=row,
            column=0,
            sticky="w",
            padx=6,
            pady=(6, 2),
        )
        self.value_var = tk.StringVar()
        self.value_entry = ttk.Entry(master, textvariable=self.value_var, width=32)
        self.value_entry.grid(row=row + 1, column=0, sticky="we", padx=6, pady=(0, 6))

        self.error_var = tk.StringVar(value="")
        ttk.Label(master, textvariable=self.error_var, foreground="red", wraplength=280).grid(
            row=row + 2, column=0, sticky="we", padx=6, pady=(0, 6)
        )

        self.columnconfigure(0, weight=1)
        master.columnconfigure(0, weight=1)

        initial_type = self._infer_type(self.initial_value)
        self.type_var.set(self.VALUE_TO_LABEL.get(initial_type, "Text"))
        self._apply_initial_value(initial_type)
        self.type_var.trace_add("write", self._on_type_change)
        return self.key_entry or type_combo

    def validate(self) -> bool:  # pragma: no cover - Tkinter tool
        key = self.key_var.get().strip()
        if self.allow_key_edit and not key:
            self.error_var.set("Key is required for dictionary entries.")
            return False

        selected_label = self.type_var.get()
        value_type = self.LABEL_TO_VALUE.get(selected_label)
        if not value_type:
            self.error_var.set("Choose a value type.")
            return False

        try:
            value = self._parse_value(value_type)
        except ValueError as exc:
            self.error_var.set(str(exc))
            return False

        self.result_data = (key if self.allow_key_edit else None, value)
        self.error_var.set("")
        return True

    def apply(self) -> None:  # pragma: no cover - Tkinter tool
        self.result = self.result_data

    def _on_type_change(self, *_: Any) -> None:
        selected_label = self.type_var.get()
        value_type = self.LABEL_TO_VALUE.get(selected_label, "string")
        if value_type in {"dict", "list", "null"}:
            self.value_entry.configure(state=tk.DISABLED)
            if value_type == "null":
                self.value_var.set("null")
            else:
                self.value_var.set("")
        else:
            self.value_entry.configure(state=tk.NORMAL)
            if value_type == "boolean" and not self.value_var.get():
                self.value_var.set("true")

    @staticmethod
    def _infer_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "float"
        if value is None:
            return "null"
        if isinstance(value, dict):
            return "dict"
        if isinstance(value, list):
            return "list"
        return "string"

    def _apply_initial_value(self, inferred_type: str) -> None:
        if inferred_type in {"dict", "list", "null"}:
            self.value_entry.configure(state=tk.DISABLED)
            if inferred_type == "null":
                self.value_var.set("null")
            else:
                self.value_var.set("")
        else:
            if inferred_type == "boolean":
                self.value_var.set("true" if self.initial_value else "false")
            else:
                self.value_var.set("" if self.initial_value is None else str(self.initial_value))

    def _parse_value(self, value_type: str) -> Any:
        text = self.value_var.get()
        if value_type == "string":
            return text
        if value_type == "integer":
            return int(text)
        if value_type == "float":
            return float(text)
        if value_type == "boolean":
            lowered = text.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
            raise ValueError("Boolean values must be true/false (or 1/0).")
        if value_type == "null":
            return None
        if value_type == "dict":
            return OrderedDict()
        if value_type == "list":
            return []
        raise ValueError("Unsupported value type.")


class WidgetDialog(tk.Toplevel):
    def __init__(self, master: tk.Widget, widget: Optional[Dict[str, Any]] = None):
        super().__init__(master)
        self.title("Widget")
        self.resizable(True, True)
        self.widget_data: Optional[Dict[str, Any]] = None

        tk.Label(self, text="Widget type (auto-filled from docs/configuration.md)").grid(row=0, column=0, sticky="w", padx=8, pady=(10, 2))
        self.type_var = tk.StringVar(value=widget.get("type", "") if widget else "")
        self.type_combo = ttk.Combobox(self, textvariable=self.type_var, values=WIDGET_TYPES, width=30)
        self.type_combo.grid(row=1, column=0, padx=8, sticky="we")
        if not self.type_var.get() and WIDGET_TYPES:
            self.type_combo.set(WIDGET_TYPES[0])
        hint_body = ", ".join(WIDGET_TYPES) if WIDGET_TYPES else "(docs/configuration.md not found)"
        hint_text = f"Widget types parsed from docs/configuration.md:\n{hint_body}"
        ttk.Label(self, text=hint_text, wraplength=320, justify="left").grid(row=2, column=0, sticky="we", padx=8, pady=(2, 8))

        tk.Label(self, text="Optional title").grid(row=3, column=0, sticky="w", padx=8, pady=(0, 2))
        self.title_var = tk.StringVar(value=widget.get("title", "") if widget else "")
        ttk.Entry(self, textvariable=self.title_var, width=30).grid(row=4, column=0, padx=8, sticky="we")

        ttk.Label(
            self,
            text=(
                "Widget options editor: add nested dictionaries/lists to match the docs.\n"
                "Use the buttons below to add siblings, drill into sub-options (e.g., bookmarks → groups → links),"
                " or import the documented example and delete/duplicate the nested titles you don't need."
            ),
            justify="left",
            wraplength=360,
        ).grid(row=5, column=0, sticky="we", padx=8, pady=(10, 2))

        self.example_button = ttk.Button(
            self,
            text="Insert example options",
            command=self.apply_example_structure,
        )
        self.example_button.grid(row=6, column=0, sticky="w", padx=8, pady=(0, 6))
        self.example_button.state(["disabled"])

        tree_container = ttk.Frame(self)
        tree_container.grid(row=7, column=0, padx=8, pady=(0, 6), sticky="nsew")
        self.rowconfigure(7, weight=1)
        tree_container.rowconfigure(0, weight=1)
        tree_container.columnconfigure(0, weight=1)

        columns = ("value",)
        self.options_tree = ttk.Treeview(tree_container, columns=columns, show="tree headings", height=8)
        self.options_tree.heading("#0", text="Option")
        self.options_tree.heading("value", text="Value / summary")
        self.options_tree.column("#0", stretch=True)
        self.options_tree.column("value", stretch=True)
        tree_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.options_tree.yview)
        self.options_tree.configure(yscrollcommand=tree_scroll.set)
        self.options_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

        button_row = ttk.Frame(self)
        button_row.grid(row=8, column=0, pady=(0, 6), padx=8, sticky="we")
        ttk.Button(button_row, text="Add option", command=self.add_option).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_row, text="Add child", command=self.add_child_option).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_row, text="Edit", command=self.edit_option).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_row, text="Delete", command=self.delete_option).pack(side=tk.LEFT, padx=2)

        self.extra_data: OrderedDict[str, Any] = OrderedDict()
        if widget:
            for key, value in widget.items():
                if key in {"type", "title"}:
                    continue
                self.extra_data[key] = _ordered_copy(value)

        self.tree_paths: Dict[str, List[Any]] = {}
        self._refresh_options_tree()

        doc_frame = ttk.LabelFrame(self, text="Widget documentation")
        doc_frame.grid(row=9, column=0, sticky="nsew", padx=8, pady=(0, 6))
        doc_frame.rowconfigure(0, weight=1)
        doc_frame.columnconfigure(0, weight=1)
        self.rowconfigure(9, weight=1)

        self.widget_doc_text = tk.Text(doc_frame, wrap="word", height=10)
        self.widget_doc_text.configure(state=tk.DISABLED)
        doc_scroll = ttk.Scrollbar(doc_frame, orient=tk.VERTICAL, command=self.widget_doc_text.yview)
        self.widget_doc_text.configure(yscrollcommand=doc_scroll.set)
        self.widget_doc_text.grid(row=0, column=0, sticky="nsew")
        doc_scroll.grid(row=0, column=1, sticky="ns")

        button_frame = tk.Frame(self)
        button_frame.grid(row=10, column=0, pady=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(button_frame, text="Save", command=self._on_save).pack(side=tk.RIGHT, padx=4)

        self.grab_set()
        self.transient(master)
        self.type_var.trace_add("write", lambda *_: self._update_doc_preview())
        self._update_doc_preview()

    def _on_save(self) -> None:
        widget_type = self.type_var.get().strip()
        if not widget_type:
            messagebox.showerror("Missing type", "Widget type is required.")
            return
        data: Dict[str, Any] = OrderedDict()
        data["type"] = widget_type
        title = self.title_var.get().strip()
        if title:
            data["title"] = title

        for key, value in self.extra_data.items():
            data[key] = value
        self.widget_data = data
        self.destroy()

    # ------------------------------------------------------------------
    # Option tree helpers
    # ------------------------------------------------------------------

    def _update_doc_preview(self) -> None:
        widget_type = self.type_var.get().strip()
        doc = WIDGET_DOC_MAP.get(widget_type)
        if not hasattr(self, "widget_doc_text"):
            return
        if hasattr(self, "example_button"):
            if doc and isinstance(doc.get("example"), dict):
                self.example_button.state(["!disabled"])
            else:
                self.example_button.state(["disabled"])
        self.widget_doc_text.configure(state=tk.NORMAL)
        self.widget_doc_text.delete("1.0", tk.END)
        if doc:
            header = doc.get("name", widget_type)
            markdown = doc.get("markdown", "").strip()
            content = f"{header} ({widget_type})\n\n{markdown}".strip()
            self.widget_doc_text.insert("1.0", content)
        elif widget_type:
            self.widget_doc_text.insert(
                "1.0",
                "No documentation excerpt was found for this widget. Run tools/update_reference_data.py to refresh docs/reference_data.json.",
            )
        else:
            self.widget_doc_text.insert(
                "1.0",
                "Select a widget type to see documentation, examples, and supported options.",
            )
        self.widget_doc_text.configure(state=tk.DISABLED)

    def apply_example_structure(self) -> None:
        widget_type = self.type_var.get().strip()
        if not widget_type:
            messagebox.showerror("Missing type", "Select a widget type before inserting the example options.")
            return
        doc = WIDGET_DOC_MAP.get(widget_type)
        example = doc.get("example") if doc else None
        if not isinstance(example, dict):
            messagebox.showinfo(
                "No example available",
                "The documentation for this widget does not expose an example YAML block.",
            )
            return
        example_copy = _ordered_copy(example)
        title_value = example_copy.get("title")
        if title_value and not self.title_var.get().strip():
            self.title_var.set(str(title_value))
        extra_from_example = self._extract_extra_from_example(example_copy)
        if not extra_from_example:
            messagebox.showinfo("Example empty", "The example snippet does not expose any additional keys.")
            return
        if not self.extra_data:
            self.extra_data = extra_from_example
            self._refresh_options_tree()
            messagebox.showinfo(
                "Example inserted",
                "Example options added. Use Add/Delete to remove groups or links you do not need.",
            )
            return
        replace = messagebox.askyesno(
            "Replace current options?",
            "Replace the existing widget options with the documented example?\n"
            "Click 'No' to merge only the missing keys.",
        )
        if replace:
            self.extra_data = extra_from_example
            self._refresh_options_tree()
            messagebox.showinfo("Example applied", "Existing widget options were replaced with the example snippet.")
            return
        added = self._merge_missing_options(self.extra_data, extra_from_example)
        if added:
            self._refresh_options_tree()
            messagebox.showinfo(
                "Example merged",
                "Missing keys from the example were added. Adjust nested titles by adding or deleting entries.",
            )
        else:
            messagebox.showinfo("No changes", "All example keys already exist in this widget.")

    def _extract_extra_from_example(self, example: Dict[str, Any]) -> OrderedDict[str, Any]:
        extra: OrderedDict[str, Any] = OrderedDict()
        for key, value in example.items():
            if key in {"type"}:
                continue
            if key == "title":
                continue
            extra[key] = _ordered_copy(value)
        return extra

    def _merge_missing_options(self, target: Any, source: Any) -> bool:
        changed = False
        if isinstance(target, dict) and isinstance(source, dict):
            for key, value in source.items():
                if key not in target:
                    target[key] = _ordered_copy(value)
                    changed = True
                else:
                    changed |= self._merge_missing_options(target[key], value)
        elif isinstance(target, list) and isinstance(source, list):
            if not target and source:
                target.extend(_ordered_copy(source))
                changed = True
            else:
                for idx, item in enumerate(target):
                    if idx < len(source):
                        changed |= self._merge_missing_options(item, source[idx])
        return changed

    def _refresh_options_tree(self) -> None:
        self.tree_paths.clear()
        for item in self.options_tree.get_children():
            self.options_tree.delete(item)
        for key, value in self.extra_data.items():
            self._insert_option_node("", key, value, [key])

    def _insert_option_node(self, parent: str, label: Any, value: Any, path: List[Any]) -> None:
        display = self._summarize_value(value)
        item_id = self.options_tree.insert(parent, "end", text=str(label), values=(display,))
        self.tree_paths[item_id] = list(path)
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                self._insert_option_node(item_id, child_key, child_value, path + [child_key])
        elif isinstance(value, list):
            for idx, child_value in enumerate(value):
                self._insert_option_node(item_id, f"[{idx}]", child_value, path + [idx])

    @staticmethod
    def _summarize_value(value: Any) -> str:
        if isinstance(value, dict):
            return f"<dict> ({len(value)} keys)"
        if isinstance(value, list):
            return f"<list> ({len(value)} items)"
        if value is None:
            return "null"
        return str(value)

    def _get_value_from_path(self, path: List[Any]) -> Any:
        current: Any = self.extra_data
        for segment in path:
            current = current[segment]
        return current

    def _get_parent_info(self, path: List[Any]) -> Tuple[Optional[Any], Optional[List[Any]], Optional[Any]]:
        if not path:
            return None, None, None
        parent_path = path[:-1]
        parent: Any = self.extra_data
        for segment in parent_path:
            parent = parent[segment]
        return parent, parent_path, path[-1]

    def add_option(self) -> None:
        selection = self.options_tree.selection()
        if not selection:
            container: Any = self.extra_data
        else:
            path = self.tree_paths[selection[0]]
            value = self._get_value_from_path(path)
            if isinstance(value, (dict, list)):
                container = value
            else:
                parent, _, _ = self._get_parent_info(path)
                container = parent if parent is not None else self.extra_data

        self._add_to_container(container)

    def add_child_option(self) -> None:
        selection = self.options_tree.selection()
        if not selection:
            messagebox.showinfo("Select option", "Select a dictionary or list to add children to.")
            return
        path = self.tree_paths[selection[0]]
        value = self._get_value_from_path(path)
        if not isinstance(value, (dict, list)):
            messagebox.showerror("Invalid selection", "You can only add children to dictionaries or lists.")
            return
        self._add_to_container(value)

    def _add_to_container(self, container: Any) -> None:
        if isinstance(container, dict):
            dialog = ValueDialog(self, "Add option", allow_key_edit=True)
            self.wait_window(dialog)
            if not dialog.result_data:
                return
            key, value = dialog.result_data
            assert key is not None
            if key in container:
                messagebox.showerror("Duplicate key", f"'{key}' already exists at this level.")
                return
            container[key] = value
        elif isinstance(container, list):
            dialog = ValueDialog(self, "Add list item", allow_key_edit=False)
            self.wait_window(dialog)
            if not dialog.result_data:
                return
            _, value = dialog.result_data
            container.append(value)
        else:
            return
        self._refresh_options_tree()

    def edit_option(self) -> None:
        selection = self.options_tree.selection()
        if not selection:
            return
        path = self.tree_paths[selection[0]]
        value = self._get_value_from_path(path)
        parent, _, key = self._get_parent_info(path)
        if parent is None:
            # Top-level entry in the root dict
            parent = self.extra_data
            key = path[0]
        allow_key = isinstance(parent, dict)
        dialog = ValueDialog(
            self,
            "Edit option",
            allow_key_edit=allow_key,
            initial_key=str(key) if allow_key else "",
            initial_value=value,
        )
        self.wait_window(dialog)
        if not dialog.result_data:
            return
        new_key, new_value = dialog.result_data
        if isinstance(parent, dict) and key is not None:
            new_key = key if new_key is None else new_key
            if new_key != key and new_key in parent:
                messagebox.showerror("Duplicate key", f"'{new_key}' already exists at this level.")
                return
            self._replace_dict_key(parent, key, new_key, new_value)
        elif isinstance(parent, list) and isinstance(key, int):
            parent[key] = new_value
        else:
            return
        self._refresh_options_tree()

    @staticmethod
    def _replace_dict_key(container: Dict[Any, Any], old_key: Any, new_key: Any, new_value: Any) -> None:
        new_items = []
        for existing_key, existing_value in container.items():
            if existing_key == old_key:
                new_items.append((new_key, new_value))
            else:
                new_items.append((existing_key, existing_value))
        container.clear()
        for k, v in new_items:
            container[k] = v

    def delete_option(self) -> None:
        selection = self.options_tree.selection()
        if not selection:
            return
        path = self.tree_paths[selection[0]]
        parent, _, key = self._get_parent_info(path)
        if parent is None:
            parent = self.extra_data
            key = path[0]
        if isinstance(parent, dict) and key in parent:
            del parent[key]
        elif isinstance(parent, list) and isinstance(key, int) and 0 <= key < len(parent):
            parent.pop(key)
        else:
            return
        self._refresh_options_tree()


class ColumnDialog(tk.Toplevel):
    def __init__(self, master: tk.Widget, column: Optional[Dict[str, Any]] = None):
        super().__init__(master)
        self.title("Column")
        self.resizable(False, False)
        self.column_data: Optional[Dict[str, Any]] = None

        ttk.Label(
            self,
            text=(
                "Column size controls layout as described in docs/configuration.md:\n"
                "use 'small' for the 300px sidebar and 'full' for flexible widths."
            ),
            wraplength=320,
            justify="left",
        ).grid(row=0, column=0, padx=8, pady=(10, 2))

        self.size_var = tk.StringVar(value=(column.get("size") if column else "small"))
        ttk.Combobox(self, textvariable=self.size_var, values=["small", "full"], state="readonly").grid(
            row=1, column=0, padx=8, pady=(0, 10)
        )

        button_frame = tk.Frame(self)
        button_frame.grid(row=2, column=0, pady=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(button_frame, text="Save", command=self._on_save).pack(side=tk.RIGHT, padx=4)

        self.grab_set()
        self.transient(master)

    def _on_save(self) -> None:
        size = self.size_var.get().strip()
        if size not in {"small", "full"}:
            messagebox.showerror("Invalid size", "Columns must be either 'small' or 'full'.")
            return
        self.column_data = {"size": size, "widgets": []}
        self.destroy()


class TkYankMaker(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Glance YAML builder")
        self.geometry("1000x700")
        self.pages: List[Dict[str, Any]] = []

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        builder_frame = ttk.Frame(notebook)
        notebook.add(builder_frame, text="Builder")

        docs_frame = ttk.Frame(notebook)
        notebook.add(docs_frame, text="Docs")

        self._build_builder_tab(builder_frame)
        self._build_docs_tab(docs_frame)
        self.update_preview()

    # ------------------------------------------------------------------
    # Builder UI
    # ------------------------------------------------------------------
    def _build_builder_tab(self, parent: ttk.Frame) -> None:
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        pages_frame = ttk.LabelFrame(container, text="Pages")
        pages_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        columns_frame = ttk.LabelFrame(container, text="Columns")
        columns_frame.grid(row=0, column=1, sticky="nsew", padx=6)

        widgets_frame = ttk.LabelFrame(container, text="Widgets")
        widgets_frame.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        preview_frame = ttk.LabelFrame(parent, text="YAML preview")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        for i in range(3):
            container.columnconfigure(i, weight=1)
        container.rowconfigure(0, weight=1)

        # Page list and actions
        self.pages_list = tk.Listbox(pages_frame, exportselection=False)
        self.pages_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.pages_list.bind("<<ListboxSelect>>", lambda _: self.refresh_columns())

        page_buttons = ttk.Frame(pages_frame)
        page_buttons.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(page_buttons, text="Add", command=self.add_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(page_buttons, text="Rename", command=self.rename_page).pack(side=tk.LEFT, padx=2)
        ttk.Button(page_buttons, text="Delete", command=self.delete_page).pack(side=tk.LEFT, padx=2)

        # Column list
        self.columns_list = tk.Listbox(columns_frame, exportselection=False)
        self.columns_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.columns_list.bind("<<ListboxSelect>>", lambda _: self.refresh_widgets())

        column_buttons = ttk.Frame(columns_frame)
        column_buttons.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(column_buttons, text="Add", command=self.add_column).pack(side=tk.LEFT, padx=2)
        ttk.Button(column_buttons, text="Edit", command=self.edit_column).pack(side=tk.LEFT, padx=2)
        ttk.Button(column_buttons, text="Delete", command=self.delete_column).pack(side=tk.LEFT, padx=2)

        # Widget list
        self.widgets_list = tk.Listbox(widgets_frame, exportselection=False)
        self.widgets_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        widget_buttons = ttk.Frame(widgets_frame)
        widget_buttons.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(widget_buttons, text="Add", command=self.add_widget).pack(side=tk.LEFT, padx=2)
        ttk.Button(widget_buttons, text="Edit", command=self.edit_widget).pack(side=tk.LEFT, padx=2)
        ttk.Button(widget_buttons, text="Delete", command=self.delete_widget).pack(side=tk.LEFT, padx=2)

        # Preview + save
        self.preview_text = tk.Text(preview_frame, height=10)
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.preview_text.configure(state=tk.DISABLED)

        button_bar = ttk.Frame(preview_frame)
        button_bar.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(button_bar, text="Load YAML", command=self.load_yaml).pack(side=tk.LEFT)
        ttk.Button(button_bar, text="Save YAML", command=self.save_yaml).pack(side=tk.RIGHT)

    def _build_docs_tab(self, parent: ttk.Frame) -> None:
        docs_notebook = ttk.Notebook(parent)
        docs_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        quick_frame = ttk.Frame(docs_notebook)
        docs_notebook.add(quick_frame, text="Quick Reference")
        doc_text = tk.Text(quick_frame, wrap="word")
        doc_text.insert("1.0", self._compose_docs_summary())
        doc_text.configure(state=tk.DISABLED)
        doc_text.pack(fill=tk.BOTH, expand=True)

        widgets_frame = ttk.Frame(docs_notebook)
        docs_notebook.add(widgets_frame, text="Widgets")
        self._build_widgets_panel(widgets_frame)

        templates_frame = ttk.Frame(docs_notebook)
        docs_notebook.add(templates_frame, text="Templates")
        self._build_templates_panel(templates_frame)

    def _build_widgets_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Widget docs scraped from docs/configuration.md (run tools/update_reference_data.py to refresh).",
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        if not WIDGETS_DATA:
            ttk.Label(parent, text="No widget metadata found; run tools/update_reference_data.py.").pack(anchor="w")
            return

        paned = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        self.widgets_doc_list = tk.Listbox(list_frame, exportselection=False)
        for widget in WIDGETS_DATA:
            label = f"{widget.get('name', 'Unknown')} ({widget.get('type', '?')})"
            self.widgets_doc_list.insert(tk.END, label)
        self.widgets_doc_list.bind("<<ListboxSelect>>", lambda _: self.show_widget_doc())
        self.widgets_doc_list.pack(fill=tk.BOTH, expand=True, padx=(0, 6))

        detail_frame = ttk.Frame(paned)
        paned.add(detail_frame, weight=3)

        self.widget_meta_var = tk.StringVar(value="Select a widget to view its documentation excerpt.")
        ttk.Label(detail_frame, textvariable=self.widget_meta_var, justify="left", wraplength=400).pack(anchor="w", pady=(0, 6))

        self.widget_doc_text = tk.Text(detail_frame, wrap="word")
        self.widget_doc_text.configure(state=tk.DISABLED)
        self.widget_doc_text.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(detail_frame)
        button_row.pack(anchor="e", pady=(6, 0))
        ttk.Button(button_row, text="Copy widget type", command=self.copy_widget_type).pack(side=tk.RIGHT, padx=4)

        if WIDGETS_DATA:
            self.widgets_doc_list.selection_set(0)
            self.show_widget_doc()

    def _build_templates_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Preconfigured templates scraped from docs/preconfigured-pages.md",
            wraplength=280,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        if not TEMPLATES:
            ttk.Label(parent, text="Run tools/update_reference_data.py to populate templates.", wraplength=280).pack(
                anchor="w"
            )
            return

        self.templates_list = tk.Listbox(parent, exportselection=False, height=6)
        for template in TEMPLATES:
            self.templates_list.insert(tk.END, template.get("name", "Unnamed"))
        self.templates_list.bind("<<ListboxSelect>>", lambda _: self.show_template_preview())
        self.templates_list.pack(fill=tk.X, pady=(0, 6))

        self.template_meta_var = tk.StringVar(value="Select a template to view its YAML.")
        ttk.Label(parent, textvariable=self.template_meta_var, wraplength=280, justify="left").pack(
            fill=tk.X, pady=(0, 6)
        )

        self.template_text = tk.Text(parent, height=18, wrap="none")
        self.template_text.configure(state=tk.DISABLED)
        self.template_text.pack(fill=tk.BOTH, expand=True)

        ttk.Button(parent, text="Copy YAML to clipboard", command=self.copy_template_yaml).pack(anchor="e", pady=(6, 0))

        if TEMPLATES:
            self.templates_list.selection_set(0)
            self.show_template_preview()

    def show_template_preview(self) -> None:
        selection = getattr(self, "templates_list", None)
        if not selection:
            return
        sel = self.templates_list.curselection()
        if not sel:
            return
        template = TEMPLATES[sel[0]]
        yaml_text = template.get("yaml", "")
        self.template_text.configure(state=tk.NORMAL)
        self.template_text.delete("1.0", tk.END)
        self.template_text.insert("1.0", yaml_text)
        self.template_text.configure(state=tk.DISABLED)

        meta_bits = []
        preview_path = template.get("preview_image")
        if preview_path:
            meta_bits.append(f"Preview: {preview_path}")
        requires = template.get("requires")
        if requires:
            meta_bits.append(f"Requires Glance {requires}")
        self.template_meta_var.set(" | ".join(meta_bits) if meta_bits else "Template metadata not provided.")

        self.current_template_yaml = yaml_text

    def copy_template_yaml(self) -> None:
        yaml_text = getattr(self, "current_template_yaml", "")
        if not yaml_text:
            messagebox.showinfo("No template selected", "Select a template first.")
            return
        self.clipboard_clear()
        self.clipboard_append(yaml_text)
        messagebox.showinfo("Copied", "Template YAML copied to clipboard.")

    def show_widget_doc(self) -> None:
        selection = getattr(self, "widgets_doc_list", None)
        if not selection:
            return
        sel = self.widgets_doc_list.curselection()
        if not sel:
            return
        widget = WIDGETS_DATA[sel[0]]
        type_name = widget.get("type", "unknown")
        title = widget.get("name", type_name)
        self.widget_meta_var.set(f"{title} — widget type: {type_name}")

        markdown = widget.get("markdown", "")
        self.widget_doc_text.configure(state=tk.NORMAL)
        self.widget_doc_text.delete("1.0", tk.END)
        self.widget_doc_text.insert("1.0", markdown)
        self.widget_doc_text.configure(state=tk.DISABLED)

        self.current_widget_type = type_name

    def copy_widget_type(self) -> None:
        widget_type = getattr(self, "current_widget_type", "")
        if not widget_type:
            messagebox.showinfo("No widget selected", "Select a widget first.")
            return
        self.clipboard_clear()
        self.clipboard_append(widget_type)
        messagebox.showinfo("Copied", f"Widget type '{widget_type}' copied to clipboard.")

    def _compose_docs_summary(self) -> str:
        sections = []
        if CONFIG_DOC.exists():
            config_text = CONFIG_DOC.read_text(encoding="utf-8")
            sections.append("--- Pages excerpt ---\n")
            sections.append(self._extract_section(config_text, "### Pages", "### Properties"))
            sections.append("\n--- Columns excerpt ---\n")
            sections.append(self._extract_section(config_text, "### Columns", "## Widgets"))
            sections.append("\n--- Widget shared properties ---\n")
            sections.append(self._extract_section(config_text, "### Shared Properties", "###"))
        if SAMPLE_CONFIG.exists():
            sections.append("\n--- Sample docs/glance.yml ---\n")
            sections.append(SAMPLE_CONFIG.read_text(encoding="utf-8"))
        return "\n".join(filter(None, sections))

    @staticmethod
    def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
        try:
            start = text.index(start_marker)
        except ValueError:
            return ""
        end = len(text)
        if end_marker:
            try:
                end = text.index(end_marker, start + len(start_marker))
            except ValueError:
                end = len(text)
        section = text[start:end]
        return section.strip()

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------
    def selected_page(self) -> Optional[Dict[str, Any]]:
        selection = self.pages_list.curselection()
        if not selection:
            return None
        return self.pages[selection[0]]

    def selected_column(self) -> Optional[Dict[str, Any]]:
        page = self.selected_page()
        if not page:
            return None
        selection = self.columns_list.curselection()
        if not selection:
            return None
        return page["columns"][selection[0]]

    def selected_widget_index(self) -> Optional[int]:
        selection = self.widgets_list.curselection()
        if not selection:
            return None
        return selection[0]

    def add_page(self) -> None:
        name = simpledialog.askstring("Page name", "Enter page name")
        if not name:
            return
        self.pages.append({"name": name, "columns": []})
        self.refresh_pages()

    def rename_page(self) -> None:
        page = self.selected_page()
        if not page:
            return
        name = simpledialog.askstring("Rename page", "New page name", initialvalue=page.get("name", ""))
        if not name:
            return
        page["name"] = name
        self.refresh_pages()

    def delete_page(self) -> None:
        selection = self.pages_list.curselection()
        if not selection:
            return
        del self.pages[selection[0]]
        self.refresh_pages()

    def add_column(self) -> None:
        page = self.selected_page()
        if not page:
            messagebox.showerror("Select page", "Add a page first (see docs/configuration.md pages section).")
            return
        dialog = ColumnDialog(self)
        self.wait_window(dialog)
        if dialog.column_data:
            page["columns"].append(dialog.column_data)
            self.refresh_columns()

    def edit_column(self) -> None:
        column = self.selected_column()
        if not column:
            return
        dialog = ColumnDialog(self, column)
        self.wait_window(dialog)
        if dialog.column_data:
            column.update(dialog.column_data)
            self.refresh_columns()

    def delete_column(self) -> None:
        page = self.selected_page()
        if not page:
            return
        selection = self.columns_list.curselection()
        if not selection:
            return
        del page["columns"][selection[0]]
        self.refresh_columns()

    def add_widget(self) -> None:
        column = self.selected_column()
        if not column:
            messagebox.showerror("Select column", "Select a column to place widgets in.")
            return
        dialog = WidgetDialog(self)
        self.wait_window(dialog)
        if dialog.widget_data:
            column["widgets"].append(dialog.widget_data)
            self.refresh_widgets()

    def edit_widget(self) -> None:
        column = self.selected_column()
        idx = self.selected_widget_index()
        if column is None or idx is None:
            return
        dialog = WidgetDialog(self, column["widgets"][idx])
        self.wait_window(dialog)
        if dialog.widget_data:
            column["widgets"][idx] = dialog.widget_data
            self.refresh_widgets()

    def delete_widget(self) -> None:
        column = self.selected_column()
        idx = self.selected_widget_index()
        if column is None or idx is None:
            return
        del column["widgets"][idx]
        self.refresh_widgets()

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------
    def refresh_pages(self) -> None:
        self.pages_list.delete(0, tk.END)
        for page in self.pages:
            self.pages_list.insert(tk.END, page.get("name", "Unnamed page"))
        self.refresh_columns()
        self.update_preview()

    def refresh_columns(self) -> None:
        self.columns_list.delete(0, tk.END)
        page = self.selected_page()
        if page:
            for column in page.get("columns", []):
                self.columns_list.insert(tk.END, f"size: {column.get('size', 'small')}")
        self.refresh_widgets()
        self.update_preview()

    def refresh_widgets(self) -> None:
        self.widgets_list.delete(0, tk.END)
        column = self.selected_column()
        if column:
            for widget in column.get("widgets", []):
                label = widget.get("title") or widget.get("type")
                self.widgets_list.insert(tk.END, label)
        self.update_preview()

    # ------------------------------------------------------------------
    # Preview + save
    # ------------------------------------------------------------------
    def load_yaml(self) -> None:
        if yaml is None:
            messagebox.showerror(
                "PyYAML not installed",
                "Loading YAML requires the PyYAML package. Install it (pip install pyyaml) and try again.",
            )
            return
        path = filedialog.askopenfilename(filetypes=[("YAML", "*.yml"), ("YAML", "*.yaml"), ("All files", "*")])
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Unable to read file", str(exc))
            return
        try:
            data = yaml.safe_load(content) or {}
        except Exception as exc:  # pragma: no cover - Tkinter tool
            messagebox.showerror("Invalid YAML", f"Could not parse YAML: {exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Invalid configuration", "Expected a dictionary at the YAML root.")
            return
        pages_data = data.get("pages")
        if not isinstance(pages_data, list):
            messagebox.showerror("Missing pages", "The YAML file must contain a top-level 'pages' list.")
            return

        self.pages = self._normalize_pages(pages_data)
        self.refresh_pages()
        if self.pages:
            self.pages_list.selection_clear(0, tk.END)
            self.pages_list.selection_set(0)
            self.refresh_columns()
        messagebox.showinfo("Loaded", f"Loaded {len(self.pages)} page(s) from {path}")

    def update_preview(self) -> None:
        config = {"pages": self.pages}
        yaml_text = to_yaml(config)
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", yaml_text)
        self.preview_text.configure(state=tk.DISABLED)

    def save_yaml(self) -> None:
        if not self.pages:
            messagebox.showerror("Empty configuration", "Add at least one page before saving.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".yml", filetypes=[("YAML", "*.yml"), ("YAML", "*.yaml")])
        if not path:
            return
        Path(path).write_text(self.preview_text.get("1.0", tk.END).strip() + "\n", encoding="utf-8")
        messagebox.showinfo("Saved", f"Configuration saved to {path}")

    @staticmethod
    def _normalize_pages(pages: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_copy: Dict[str, Any] = OrderedDict()
            for key, value in page.items():
                if key == "columns":
                    continue
                page_copy[key] = _ordered_copy(value)
            columns_list: List[Dict[str, Any]] = []
            columns = page.get("columns")
            if isinstance(columns, list):
                for column in columns:
                    if not isinstance(column, dict):
                        continue
                    column_copy: Dict[str, Any] = OrderedDict()
                    for key, value in column.items():
                        if key == "widgets":
                            continue
                        column_copy[key] = _ordered_copy(value)
                    widgets: List[Dict[str, Any]] = []
                    raw_widgets = column.get("widgets")
                    if isinstance(raw_widgets, list):
                        for widget in raw_widgets:
                            if isinstance(widget, dict):
                                widgets.append(_ordered_copy(widget))
                    column_copy.setdefault("size", column.get("size", "small"))
                    column_copy["widgets"] = widgets
                    columns_list.append(column_copy)
            page_copy.setdefault("name", page.get("name", "Page"))
            page_copy["columns"] = columns_list
            normalized.append(page_copy)
        return normalized


def main() -> None:
    app = TkYankMaker()
    app.mainloop()


if __name__ == "__main__":
    main()
