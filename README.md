# Przeglądarka stacków (Python + tkinter)

Prosta aplikacja do etykietowania ~1100 stacków (max z 5 klatek) **w kolejności czasowej**, z podglądem **poprzedni | bieżący | następny**.

Bez Javy, bez Electrona, bez Qt — tylko **Python + tkinter** (wbudowany) i **Pillow** (obrazy PNG/JPG).

## Co zainstalować na Windows

1. **Python 3.12** z [python.org](https://www.python.org/downloads/)  
   - zaznacz **Add python.exe to PATH**  
   - 3.12 nie działa na Windows 7 (potrzebujesz Win 10/11)
2. W PowerShellu / cmd, w tym folderze:

```bat
cd python-labeler
python -m pip install -r requirements.txt
python main.py
```

Albo po sklonowaniu całego repo:

```bat
cd multi-frame-sky-labeler\python-labeler
python -m pip install -r requirements.txt
python main.py
```

## Co robi każdy plik

| Plik | Rola |
|------|------|
| `main.py` | Start programu — tworzy okno i łączy logikę z GUI |
| `logic.py` | **Logika:** folder, sortowanie, nawigacja, boxy, statusy, zapis/odczyt `etykiety.json` |
| `gui.py` | **Interfejs:** lista plików, 3 obrazy, przyciski, mysz, skróty klawiszowe |
| `requirements.txt` | Zależność: Pillow |
| `README.md` | Ta instrukcja |

## Przepływ

1. **Otwórz folder** ze stackami (posortują się jak w eksploratorze).
2. Na **środkowym** obrazie rysujesz prostokąt i wybierasz klasę (1–5).
3. Sąsiadów używasz tylko do porównania (flara znika / meteor się przesuwa).
4. **Zapisz etykiety** (S) → zawsze `etykiety.json` w folderze ze stackami. Przy kolejnym **Otwórz folder** ten plik wczytuje się automatycznie.
   - Kółko myszy = zoom do kursora, prawy/środkowy przycisk = przesuwanie powiększonego obrazu, `0` = reset.
5. Później (osobny skrypt) do treningu 3-klatkowego: dla każdego oznaczonego pliku \(t\) dokładasz automatycznie \(t-1\) i \(t+1\).

## Skróty

| Klawisz | Akcja |
|---------|--------|
| A / ←, D / → | Sąsiedni stack |
| 1–5 | Klasa |
| E | Oznacz jako puste i dalej |
| Enter | Zapisz status i dalej |
| Backspace | Cofnij ostatni box |
| S | Zapisz JSON |

## Wyjście (`etykiety.json`)

Dla każdego pliku: `status` (`unreviewed` / `reviewed` / `empty`) oraz lista boxów (`class_id`, `x`, `y`, `w`, `h` w zakresie 0–1).
