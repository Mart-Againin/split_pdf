#!/usr/bin/env python3
"""Интерактивное разделение PDF-файла на части."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

SCRIPT_DIR = Path(__file__).resolve().parent


def list_pdfs() -> list[Path]:
    return sorted(
        p for p in SCRIPT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )


def ask_int(prompt: str, lo: int, hi: int, attempts: int = 3) -> int:
    for _ in range(attempts):
        raw = input(prompt).strip()
        try:
            val = int(raw)
        except ValueError:
            print(f"Введите целое число от {lo} до {hi}.")
            continue
        if lo <= val <= hi:
            return val
        print(f"Число вне диапазона {lo}..{hi}.")
    print("Слишком много неудачных попыток.")
    sys.exit(1)


def ask_yes_no(prompt: str) -> bool:
    while True:
        raw = input(f"{prompt} (y/n): ").strip().lower()
        if raw in ("y", "yes", "д", "да"):
            return True
        if raw in ("n", "no", "н", "нет"):
            return False
        print("Ответьте y или n.")


def open_pdf(path: Path):
    reader = PdfReader(str(path))
    if not reader.is_encrypted:
        return reader
    for _ in range(3):
        pwd = getpass.getpass(f"Файл '{path.name}' защищён паролем. Пароль: ")
        try:
            if reader.decrypt(pwd) > 0:
                return reader
        except Exception:
            pass
        print("Неверный пароль.")
    print("Не удалось открыть PDF. Пропускаем.")
    return None


def parse_sizes(raw: str) -> list[int]:
    cleaned = raw.replace(" ", ",").replace(";", ",")
    parts = [p for p in cleaned.split(",") if p.strip()]
    return [int(p) for p in parts]


def compute_ranges(mode: str, total: int, n: int | None = None,
                   sizes: list[int] | None = None) -> list[tuple[int, int]]:
    if mode == "pages":
        return [(i, i) for i in range(1, total + 1)]

    if mode == "fixed":
        ranges, start = [], 1
        while start <= total:
            end = min(start + n - 1, total)
            ranges.append((start, end))
            start = end + 1
        return ranges

    if mode == "list":
        ranges, start = [], 1
        for size in sizes:  # type: ignore[union-attr]
            end = min(start + size - 1, total)
            ranges.append((start, end))
            start = end + 1
            if start > total:
                break
        if start <= total and ranges:
            # остаток «добирает» последний блок
            ranges[-1] = (ranges[-1][0], total)
        return ranges

    raise ValueError(mode)


def write_block(reader, start: int, end: int, path: Path) -> None:
    writer = PdfWriter()
    for p in range(start, end + 1):
        writer.add_page(reader.pages[p - 1])
    with path.open("wb") as f:
        writer.write(f)


def main() -> None:
    pdfs = list_pdfs()
    if not pdfs:
        print(f"В папке '{SCRIPT_DIR}' нет PDF-файлов.")
        sys.exit(1)

    print(f"В папке '{SCRIPT_DIR}' найдены PDF-файлы:")
    for i, p in enumerate(pdfs, 1):
        print(f"  {i}. {p.name}")

    if len(pdfs) == 1:
        chosen = pdfs[0]
        print(f"\nВыбран единственный файл: {chosen.name}")
    else:
        idx = ask_int(f"\nКакой файл разделить? Номер (1-{len(pdfs)}): ",
                      1, len(pdfs))
        chosen = pdfs[idx - 1]

    reader = open_pdf(chosen)
    if reader is None:
        sys.exit(1)
    total = len(reader.pages)
    if total == 0:
        print("В PDF нет страниц.")
        sys.exit(1)
    print(f"Всего страниц: {total}")

    print("\nВыберите тип деления:")
    print("  1. постранично")
    print("  2. на блоки фиксированного размера n")
    print("  3. на блоки по списку длин")
    choice = ask_int("Номер (1-3): ", 1, 3)

    if choice == 1:
        mode = "pages"
        ranges = compute_ranges("pages", total)
        out_dir = SCRIPT_DIR / f"{chosen.stem}_pages"

    elif choice == 2:
        mode = "fixed"
        n = ask_int(f"Сколько страниц в каждом блоке (1-{total})? ", 1, total)
        ranges = compute_ranges("fixed", total, n=n)
        out_dir = SCRIPT_DIR / f"{chosen.stem}_blocks"
        last = ranges[-1][1] - ranges[-1][0] + 1
        if last < n:
            print(f"Последний блок: {last} стр. (меньше {n}).")

    else:
        mode = "list"
        out_dir = SCRIPT_DIR / f"{chosen.stem}_blocks"
        while True:
            raw = input(
                "Введите длины блоков через запятую или пробел "
                "(например 3, 7, 2, 2, 4): "
            )
            try:
                sizes = parse_sizes(raw)
            except ValueError:
                print("Не удалось разобрать список. Повторите.")
                continue
            if not sizes or any(s <= 0 for s in sizes):
                print("Все размеры должны быть положительными.")
                continue
            s = sum(sizes)
            if s > total:
                print(f"Сумма {s} больше общего числа страниц {total}. "
                      f"Повторите ввод.")
                continue
            if s < total:
                print(f"Сумма {s} меньше {total}. "
                      f"Остаток {total - s} стр. "
                      f"будет добавлен к последнему блоку.")
            ranges = compute_ranges("list", total, sizes=sizes)
            break

    out_dir.mkdir(parents=True, exist_ok=True)

    page_digits = max(3, len(str(total)))
    block_digits = max(2, len(str(len(ranges))))

    file_entries: list[tuple[Path, int, int]] = []
    for i, (start, end) in enumerate(ranges, 1):
        if mode == "pages":
            name = f"{chosen.stem}_page_{start:0{page_digits}d}.pdf"
        else:
            name = (
                f"{chosen.stem}_block_{i:0{block_digits}d}"
                f"_p{start:0{page_digits}d}-{end:0{page_digits}d}.pdf"
            )
        file_entries.append((out_dir / name, start, end))

    existing = [p for p, _, _ in file_entries if p.exists()]
    overwrite = False
    if existing:
        print(f"\nВ '{out_dir}' уже есть {len(existing)} файлов "
              f"с такими именами.")
        overwrite = ask_yes_no("Перезаписать их?")

    print(f"\nСоздаётся файлов: {len(file_entries)}")
    written = skipped = 0
    for idx, (path, start, end) in enumerate(file_entries, 1):
        if path.exists() and not overwrite:
            skipped += 1
            continue
        write_block(reader, start, end, path)
        written += 1
        if len(file_entries) <= 100:
            print(f"  {path.name}")
        elif idx % 100 == 0:
            print(f"  ... {idx}/{len(file_entries)}")

    print(f"\nГотово. Создано: {written}, пропущено: {skipped}.")
    print(f"Результат в: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано.")
        sys.exit(130)