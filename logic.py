"""Logika aplikacji — bez GUI.

Odpowiada za:
- wczytanie i posortowanie stacków z folderu,
- nawigację prev / current / next,
- przechowywanie etykiet (boxy + status),
- zapis / odczyt pliku etykiety JSON.
"""

from __future__ import annotations

import json
import random
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

LabelClass = Literal[
    "meteor",
    "satelita",
    "flara satelitarna",
    "samolot",
    "Cosmic ray",
    "Sensor artefact",
]

FrameStatus = Literal["unreviewed", "reviewed", "empty"]

# Tryb zapisu JSON pod późniejszy trening
ExportMode = Literal["single", "triplet"]

# Klasy widoczne w GUI: id → (nazwa, skrót klawiszowy)
CLASSES: list[tuple[LabelClass, str, str]] = [
    ("meteor", "Meteor", "1"),
    ("satelita", "Satelita", "2"),
    ("flara satelitarna", "Flara satelitarna", "3"),
    ("samolot", "Samolot", "4"),
    ("Cosmic ray", "Cosmic ray", "5"),
    ("Sensor artefact", "Sensor artefact", "6"),
]


@dataclass
class Box:
    """Prostokąt w współrzędnych znormalizowanych 0–1 względem obrazu."""

    class_id: LabelClass
    x: float
    y: float
    w: float
    h: float

    def clamp(self) -> Box:
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return Box(self.class_id, x, y, w, h)


@dataclass
class FrameLabel:
    file_name: str
    status: FrameStatus = "unreviewed"
    boxes: list[Box] = field(default_factory=list)


def natural_key(name: str) -> list:
    """Sortowanie jak w eksploratorze: stack_2 przed stack_10."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def list_image_files(folder: Path) -> list[Path]:
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: natural_key(p.name))


class LabelAppLogic:
    """Stan sekwencji stacków + etykiet."""

    def __init__(self) -> None:
        self.folder: Path | None = None
        self.files: list[Path] = []
        self.index: int = 0
        self.labels: dict[str, FrameLabel] = {}
        self.active_class: LabelClass = "meteor"
        self.labels_path: Path | None = None

    # --- folder / nawigacja -------------------------------------------------

    def open_folder(self, folder: Path, labels_path: Path | None = None) -> int:
        folder = folder.resolve()
        if not folder.is_dir():
            raise NotADirectoryError(folder)
        files = list_image_files(folder)
        self.folder = folder
        self.files = files
        self.index = 0
        self.labels = {}
        self.labels_path = labels_path or (folder / "etykiety.json")
        if self.labels_path.is_file():
            self.load_labels(self.labels_path)
        return len(files)

    def count(self) -> int:
        return len(self.files)

    def current_path(self) -> Path | None:
        if not self.files:
            return None
        return self.files[self.index]

    def prev_path(self) -> Path | None:
        if self.index <= 0 or not self.files:
            return None
        return self.files[self.index - 1]

    def next_path(self) -> Path | None:
        if not self.files or self.index >= len(self.files) - 1:
            return None
        return self.files[self.index + 1]

    def go(self, delta: int) -> None:
        if not self.files:
            return
        self.index = min(max(self.index + delta, 0), len(self.files) - 1)

    def go_to(self, index: int) -> None:
        if not self.files:
            return
        self.index = min(max(index, 0), len(self.files) - 1)

    # --- etykiety -----------------------------------------------------------

    def _ensure_label(self) -> FrameLabel | None:
        path = self.current_path()
        if path is None:
            return None
        key = path.name
        if key not in self.labels:
            self.labels[key] = FrameLabel(file_name=key)
        return self.labels[key]

    def current_label(self) -> FrameLabel | None:
        path = self.current_path()
        if path is None:
            return None
        return self.labels.get(path.name) or FrameLabel(file_name=path.name)

    def set_active_class(self, class_id: LabelClass) -> None:
        self.active_class = class_id

    def add_box(self, x: float, y: float, w: float, h: float) -> Box | None:
        lab = self._ensure_label()
        if lab is None:
            return None
        box = Box(self.active_class, x, y, w, h).clamp()
        if box.w < 0.004 or box.h < 0.004:
            return None
        lab.boxes.append(box)
        lab.status = "reviewed"
        return box

    def clear_boxes(self) -> None:
        lab = self._ensure_label()
        if lab is None:
            return
        lab.boxes.clear()

    def delete_last_box(self) -> None:
        lab = self._ensure_label()
        if lab is None or not lab.boxes:
            return
        lab.boxes.pop()
        if not lab.boxes and lab.status == "reviewed":
            lab.status = "unreviewed"

    def mark_empty(self) -> None:
        lab = self._ensure_label()
        if lab is None:
            return
        lab.boxes.clear()
        lab.status = "empty"

    def mark_reviewed_and_next(self) -> None:
        lab = self._ensure_label()
        if lab is None:
            return
        if lab.status != "empty":
            lab.status = "reviewed" if lab.boxes else "empty"
        self.go(1)

    def stats(self) -> dict[str, int]:
        reviewed = empty = boxes = 0
        for lab in self.labels.values():
            if lab.status == "reviewed":
                reviewed += 1
            elif lab.status == "empty":
                empty += 1
            boxes += len(lab.boxes)
        return {
            "total": len(self.files),
            "reviewed": reviewed,
            "empty": empty,
            "boxes": boxes,
            "touched": reviewed + empty,
        }

    # --- JSON ---------------------------------------------------------------

    def neighbors_for(self, file_name: str) -> tuple[str | None, str | None]:
        """Zwraca (prev, next) nazwy plików dla danej klatki w posortowanej liście."""
        names = [p.name for p in self.files]
        try:
            i = names.index(file_name)
        except ValueError:
            return None, None
        prev = names[i - 1] if i > 0 else None
        nxt = names[i + 1] if i < len(names) - 1 else None
        return prev, nxt

    def save_labels(
        self,
        path: Path | None = None,
        mode: ExportMode = "single",
    ) -> Path:
        """Zapisz etykiety.

        mode='single'  — tylko bieżący plik + boxy (trening 1-klatkowy).
        mode='triplet' — do każdej klatki dopisuje prev/next z kolejności folderu
                         (trening 3-klatkowy); boxy nadal dotyczą current.
        """
        out = path or self.labels_path
        if out is None:
            raise ValueError("Brak ścieżki zapisu etykiet")
        if mode == "triplet":
            note = (
                "Eksport TRIPLET: boxy dotyczą current. Pola prev_file / next_file "
                "wiążą sąsiadów z tej samej sekwencji. Brak sąsiada → complete=false "
                "(brzeg nocy / listy)."
            )
        else:
            note = (
                "Eksport SINGLE: jedna klatka + boxy. Sąsiedzi nie są zapisani — "
                "pod trening 1-klatkowy."
            )
        payload: dict = {
            "version": 2,
            "export_mode": mode,
            "folder": str(self.folder) if self.folder else None,
            "note": note,
            "classes": [
                {"id": cid, "name": name, "shortcut": key}
                for cid, name, key in CLASSES
            ],
            "frames": [],
        }
        seen: set[str] = set()
        for p in self.files:
            lab = self.labels.get(p.name, FrameLabel(file_name=p.name))
            seen.add(p.name)
            payload["frames"].append(self._frame_dict(lab, mode))
        for name, lab in self.labels.items():
            if name not in seen:
                payload["frames"].append(self._frame_dict(lab, mode))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.labels_path = out
        return out

    def _frame_dict(self, lab: FrameLabel, mode: ExportMode) -> dict:
        entry: dict = {
            "file_name": lab.file_name,
            "status": lab.status,
            "boxes": [asdict(b) for b in lab.boxes],
        }
        if mode == "triplet":
            prev, nxt = self.neighbors_for(lab.file_name)
            entry["prev_file"] = prev
            entry["next_file"] = nxt
            entry["complete"] = prev is not None and nxt is not None
        return entry

    def load_labels(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        frames = data.get("frames", [])
        loaded: dict[str, FrameLabel] = {}
        for item in frames:
            boxes = [
                Box(
                    class_id=b["class_id"],
                    x=float(b["x"]),
                    y=float(b["y"]),
                    w=float(b["w"]),
                    h=float(b["h"]),
                )
                for b in item.get("boxes", [])
            ]
            loaded[item["file_name"]] = FrameLabel(
                file_name=item["file_name"],
                status=item.get("status", "unreviewed"),
                boxes=boxes,
            )
        self.labels = loaded
        self.labels_path = path

    def triplet_names(self) -> tuple[str | None, str | None, str | None]:
        """Nazwy plików (prev, current, next) — pod późniejszy eksport 3-klatkowy."""
        cur = self.current_path()
        prev = self.prev_path()
        nxt = self.next_path()
        return (
            prev.name if prev else None,
            cur.name if cur else None,
            nxt.name if nxt else None,
        )

    def path_by_name(self, name: str) -> Path | None:
        for p in self.files:
            if p.name == name:
                return p
        return None

    def collect_export_samples(
        self,
        mode: ExportMode,
        *,
        include_empty: bool = True,
        only_with_boxes: bool = False,
    ) -> list[FrameLabel]:
        """Klatki kwalifikujące się do zbioru (jednostka podziału = current)."""
        out: list[FrameLabel] = []
        for p in self.files:
            lab = self.labels.get(p.name)
            if lab is None:
                continue
            if lab.status == "unreviewed":
                continue
            if lab.status == "empty" and not include_empty:
                continue
            if only_with_boxes and not lab.boxes:
                continue
            if mode == "triplet":
                prev, nxt = self.neighbors_for(lab.file_name)
                if prev is None or nxt is None:
                    continue
            out.append(lab)
        return out

    @staticmethod
    def split_counts(
        n: int, train_pct: float, val_pct: float, test_pct: float
    ) -> tuple[int, int, int]:
        """Policz ile próbek do train/val/test. Procenty ~100; reszta → train."""
        if n <= 0:
            return 0, 0, 0
        total = train_pct + val_pct + test_pct
        if total <= 0:
            raise ValueError("Suma procentów musi być > 0")
        train_pct, val_pct, test_pct = (
            100 * train_pct / total,
            100 * val_pct / total,
            100 * test_pct / total,
        )
        n_train = int(n * train_pct / 100)
        n_val = int(n * val_pct / 100)
        n_test = n - n_train - n_val  # reszta → test, potem korekta
        # przy bardzo małych n zapewnij sensowne minima
        if n >= 3 and min(train_pct, val_pct, test_pct) > 0:
            if n_train == 0:
                n_train = 1
            if n_val == 0:
                n_val = 1
            if n_test == 0:
                n_test = 1
            while n_train + n_val + n_test > n:
                if n_train >= n_val and n_train >= n_test and n_train > 1:
                    n_train -= 1
                elif n_val >= n_test and n_val > 1:
                    n_val -= 1
                elif n_test > 1:
                    n_test -= 1
                else:
                    break
            # dobierz resztę do train
            rem = n - (n_train + n_val + n_test)
            n_train += rem
        else:
            n_test = n - n_train - n_val
        return n_train, n_val, n_test

    def build_dataset(
        self,
        dest: Path,
        mode: ExportMode,
        train_pct: float,
        val_pct: float,
        test_pct: float,
        *,
        include_empty: bool = True,
        only_with_boxes: bool = False,
        seed: int = 42,
        yolo_format: bool = False,
    ) -> dict:
        """Skopiuj próbki do dest i zapisz manifest.

        yolo_format=False:
          dest/{train,val,test}/<id>/{prev?,current,next?,label.json}
        yolo_format=True (Ultralytics):
          dest/images/{train,val,test}/ + dest/labels/... + dest/data.yaml
          (zawsze tylko current — YOLO nie bierze tripletów natywnie)
        """
        if not self.files or self.folder is None:
            raise ValueError("Najpierw otwórz folder ze stackami")

        samples = self.collect_export_samples(
            mode, include_empty=include_empty, only_with_boxes=only_with_boxes
        )
        if not samples:
            raise ValueError(
                "Brak próbek do eksportu (oznacz reviewed/empty; przy triplet potrzebne sąsiedzi)."
            )

        rng = random.Random(seed)
        order = samples[:]
        rng.shuffle(order)
        n_train, n_val, n_test = self.split_counts(
            len(order), train_pct, val_pct, test_pct
        )
        buckets = {
            "train": order[:n_train],
            "val": order[n_train : n_train + n_val],
            "test": order[n_train + n_val :],
        }

        dest = dest.resolve()
        dest.mkdir(parents=True, exist_ok=True)

        if yolo_format:
            written = self._write_yolo_dataset(dest, buckets, mode)
            note = (
                "Format Ultralytics YOLO: images/ + labels/ (.txt cx cy w h) + data.yaml. "
                "Eksportuje tylko current (nawet jeśli wybór próbek był triplet)."
            )
        else:
            written = self._write_sample_dataset(dest, buckets, mode)
            note = (
                "Podział losowy po próbkach (current). Przy triplet każda próbka ma "
                "prev/current/next; boxy w label.json dotyczą current."
            )

        class_list = [
            {"id": cid, "name": name, "shortcut": key}
            for cid, name, key in CLASSES
        ]
        manifest = {
            "version": 1,
            "export_mode": mode,
            "yolo_format": yolo_format,
            "source_folder": str(self.folder),
            "destination": str(dest),
            "seed": seed,
            "percentages": {
                "train": train_pct,
                "val": val_pct,
                "test": test_pct,
            },
            "counts": {k: len(v) for k, v in written.items()},
            "samples": written,
            "classes": class_list,
            "note": note,
        }
        if yolo_format:
            manifest["data_yaml"] = str(dest / "data.yaml")
        (dest / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (dest / "classes.json").write_text(
            json.dumps(class_list, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return manifest

    def _write_sample_dataset(
        self,
        dest: Path,
        buckets: dict[str, list[FrameLabel]],
        mode: ExportMode,
    ) -> dict[str, list[str]]:
        written: dict[str, list[str]] = {"train": [], "val": [], "test": []}
        for split, labs in buckets.items():
            split_dir = dest / split
            split_dir.mkdir(parents=True, exist_ok=True)
            for lab in labs:
                sample_id = Path(lab.file_name).stem
                sample_dir = split_dir / sample_id
                if sample_dir.exists():
                    shutil.rmtree(sample_dir)
                sample_dir.mkdir(parents=True)

                cur_path = self.path_by_name(lab.file_name)
                if cur_path is None:
                    continue
                shutil.copy2(cur_path, sample_dir / f"current{cur_path.suffix.lower()}")

                label_payload: dict = {
                    "sample_id": sample_id,
                    "split": split,
                    "export_mode": mode,
                    "file_name": lab.file_name,
                    "status": lab.status,
                    "boxes": [asdict(b) for b in lab.boxes],
                }

                if mode == "triplet":
                    prev_name, next_name = self.neighbors_for(lab.file_name)
                    assert prev_name and next_name
                    prev_path = self.path_by_name(prev_name)
                    next_path = self.path_by_name(next_name)
                    if prev_path is None or next_path is None:
                        shutil.rmtree(sample_dir)
                        continue
                    shutil.copy2(prev_path, sample_dir / f"prev{prev_path.suffix.lower()}")
                    shutil.copy2(next_path, sample_dir / f"next{next_path.suffix.lower()}")
                    label_payload["prev_file"] = prev_name
                    label_payload["next_file"] = next_name
                    label_payload["complete"] = True

                (sample_dir / "label.json").write_text(
                    json.dumps(label_payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                written[split].append(sample_id)
        return written

    def _write_yolo_dataset(
        self,
        dest: Path,
        buckets: dict[str, list[FrameLabel]],
        mode: ExportMode,
    ) -> dict[str, list[str]]:
        """Ultralytics layout: images/{split}/ + labels/{split}/*.txt + data.yaml."""
        class_to_idx = {cid: i for i, (cid, _n, _k) in enumerate(CLASSES)}
        names = [name for _cid, name, _k in CLASSES]
        written: dict[str, list[str]] = {"train": [], "val": [], "test": []}

        for split, labs in buckets.items():
            img_dir = dest / "images" / split
            lbl_dir = dest / "labels" / split
            img_dir.mkdir(parents=True, exist_ok=True)
            lbl_dir.mkdir(parents=True, exist_ok=True)
            for lab in labs:
                cur_path = self.path_by_name(lab.file_name)
                if cur_path is None:
                    continue
                sample_id = Path(lab.file_name).stem
                ext = cur_path.suffix.lower()
                dst_img = img_dir / f"{sample_id}{ext}"
                shutil.copy2(cur_path, dst_img)

                lines: list[str] = []
                for b in lab.boxes:
                    idx = class_to_idx.get(b.class_id)
                    if idx is None:
                        continue
                    cx = b.x + b.w / 2.0
                    cy = b.y + b.h / 2.0
                    lines.append(
                        f"{idx} {cx:.6f} {cy:.6f} {b.w:.6f} {b.h:.6f}"
                    )
                (lbl_dir / f"{sample_id}.txt").write_text(
                    "\n".join(lines) + ("\n" if lines else ""),
                    encoding="utf-8",
                )
                written[split].append(sample_id)

        # data.yaml — ścieżki względne względem pliku yaml
        yaml_lines = [
            f"path: {dest.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "names:",
        ]
        for i, name in enumerate(names):
            yaml_lines.append(f"  {i}: {name}")
        if mode == "triplet":
            yaml_lines.append(
                "# note: sample selection may require triplet neighbors,"
                " but images are current-only for YOLO"
            )
        (dest / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        return written
