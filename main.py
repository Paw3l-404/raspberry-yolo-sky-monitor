"""Punkt startowy aplikacji.

Uruchomienie (Windows / WSL / Linux):

    cd python-labeler
    python -m pip install -r requirements.txt
    python main.py

Nie zawiera logiki ani layoutu — tylko skleja logic + gui.
"""

from __future__ import annotations

import tkinter as tk

from gui import LabelAppGui
from logic import LabelAppLogic


def main() -> None:
    root = tk.Tk()
    logic = LabelAppLogic()
    LabelAppGui(root, logic)
    root.mainloop()


if __name__ == "__main__":
    main()
