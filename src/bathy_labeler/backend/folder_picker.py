from __future__ import annotations


def choose_directory(title: str = "Select Folder", initial_dir: str | None = None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:  # pragma: no cover - depends on local Python build
        raise RuntimeError("Native folder picker is unavailable because tkinter is not installed.") from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on local desktop availability
        raise RuntimeError("Native folder picker could not open on this desktop session.") from exc

    try:
        root.withdraw()
        root.update_idletasks()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=root,
            title=title,
            initialdir=initial_dir or None,
            mustexist=False,
        )
    except tk.TclError as exc:  # pragma: no cover - depends on local desktop availability
        raise RuntimeError("Native folder picker could not open on this desktop session.") from exc
    finally:
        root.destroy()
    return selected or None
