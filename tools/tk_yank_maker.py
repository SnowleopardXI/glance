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
from typing import Any, Dict, List, Optional

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


class WidgetDialog(tk.Toplevel):
    def __init__(self, master: tk.Widget, widget: Optional[Dict[str, Any]] = None):
        super().__init__(master)
        self.title("Widget")
        self.resizable(False, False)
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

        tk.Label(
            self,
            text=(
                "Extra options as key=value pairs, one per line.\n"
                "Examples include `location=London, United Kingdom` for weather widgets\n"
                "or `limit=10`/`cache=12h` for feeds as described in docs/configuration.md."
            ),
            justify="left",
            wraplength=320,
        ).grid(row=5, column=0, sticky="we", padx=8, pady=(10, 2))

        self.options_text = tk.Text(self, width=40, height=6)
        if widget:
            extras = []
            for key, val in widget.items():
                if key in {"type", "title"}:
                    continue
                extras.append(f"{key}={val}")
            self.options_text.insert("1.0", "\n".join(extras))
        self.options_text.grid(row=6, column=0, padx=8, pady=(0, 10))

        button_frame = tk.Frame(self)
        button_frame.grid(row=7, column=0, pady=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(button_frame, text="Save", command=self._on_save).pack(side=tk.RIGHT, padx=4)

        self.grab_set()
        self.transient(master)
        self.type_var.trace_add("write", lambda *_: None)

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

        extra_text = self.options_text.get("1.0", tk.END).strip()
        if extra_text:
            for line in extra_text.splitlines():
                if not line.strip():
                    continue
                if "=" not in line:
                    messagebox.showerror(
                        "Invalid option",
                        "Each option must use the key=value format (see docs/configuration.md shared widget properties).",
                    )
                    return
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
        self.widget_data = data
        self.destroy()


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

        save_button = ttk.Button(preview_frame, text="Save YAML", command=self.save_yaml)
        save_button.pack(anchor="e", padx=6, pady=(0, 6))

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


def main() -> None:
    app = TkYankMaker()
    app.mainloop()


if __name__ == "__main__":
    main()
