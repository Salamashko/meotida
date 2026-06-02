# -*- coding: utf-8 -*-
r"""
Обновление Wiki-базы по двум отдельным экспортам:
1) публичные инструкции
2) внутренние инструкции

Что делает скрипт:
- сравнивает старую публичную базу с новой публичной базой;
- сравнивает старую внутреннюю базу с новой внутренней базой;
- собирает новую общую базу для HTML-приложения;
- ставит метки доступа:
  public   = публичная инструкция
  internal = внутренняя инструкция
- создаёт отчёт, что добавилось, удалилось и изменилось.

Когда нужен:
После того как ты скачала два свежих XAR из Wiki:
- wiki_public_YYYYMMDD.xar
- wiki_internal_YYYYMMDD.xar

и прогнала каждый через xar_to_json.py.

Как запускать:
python update_wiki_public_internal.py
"""

import csv
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def clean_path(raw: str) -> Path:
    raw = raw.strip().strip('"').strip("'")
    return Path(raw).expanduser()


def ask_file(label: str, required: bool = True) -> Path | None:
    while True:
        print("")
        raw = input(label + "\nВставь путь к файлу и нажми Enter" + ("." if required else ". Если файла нет, просто нажми Enter.") + "\n> ").strip()

        if not raw and not required:
            return None

        path = clean_path(raw)

        if path.exists() and path.is_file():
            return path

        print("Не нашла такой файл. Проверь путь и попробуй ещё раз.")


def load_json_or_js(path: Path):
    text = path.read_text(encoding="utf-8-sig").strip()

    if text.startswith("window.WIKI_KNOWLEDGE_BASE"):
        text = re.sub(r"^window\.WIKI_KNOWLEDGE_BASE\s*=\s*", "", text)
        text = text.rstrip(";").strip()

    data = json.loads(text)

    if not isinstance(data, list):
        raise ValueError(f"Файл {path} должен содержать JSON-массив: [{{...}}, {{...}}]")

    return data


def normalize_key(doc: dict) -> str:
    url = (doc.get("url") or "").strip().lower()
    if url:
        return url.rstrip("/")

    doc_id = (doc.get("id") or "").strip().lower()
    return doc_id


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def doc_hash(doc: dict) -> str:
    payload = {
        "title": normalize_text(doc.get("title")),
        "url": normalize_text(doc.get("url")),
        "section": normalize_text(doc.get("section")),
        "pathText": normalize_text(doc.get("pathText")),
        "text": normalize_text(doc.get("text")),
        "keywords": [normalize_text(x) for x in doc.get("keywords", [])],
        "attachments": [normalize_text(x) for x in doc.get("attachments", [])],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def index_docs(docs):
    result = {}
    duplicates = []

    for doc in docs:
        key = normalize_key(doc)
        if not key:
            continue

        if key in result:
            duplicates.append(doc)
            continue

        result[key] = doc

    return result, duplicates


def diff_docs(old_docs, new_docs, label):
    old_docs = old_docs or []
    new_docs = new_docs or []

    old_index, old_duplicates = index_docs(old_docs)
    new_index, new_duplicates = index_docs(new_docs)

    rows = []
    added = []
    removed = []
    changed = []
    unchanged = []

    all_keys = sorted(set(old_index.keys()) | set(new_index.keys()))

    for key in all_keys:
        old_doc = old_index.get(key)
        new_doc = new_index.get(key)

        if old_doc and not new_doc:
            status = "removed"
            doc = old_doc
            removed.append(doc)
        elif new_doc and not old_doc:
            status = "added"
            doc = new_doc
            added.append(doc)
        else:
            old_hash = doc_hash(old_doc)
            new_hash = doc_hash(new_doc)
            doc = new_doc

            if old_hash != new_hash:
                status = "changed"
                changed.append(doc)
            else:
                status = "unchanged"
                unchanged.append(doc)

        rows.append({
            "status": status,
            "accessGroup": label,
            "title": doc.get("title", ""),
            "url": doc.get("url", ""),
            "section": doc.get("section", ""),
            "pathText": doc.get("pathText", ""),
            "textLength": len(doc.get("text", "") or ""),
            "attachmentsCount": doc.get("attachmentsCount", ""),
        })

    return {
        "rows": rows,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "old_count": len(old_docs),
        "new_count": len(new_docs),
        "old_duplicates": old_duplicates,
        "new_duplicates": new_duplicates,
    }


def mark_doc(doc: dict, access_group: str) -> dict:
    copy_doc = dict(doc)

    if access_group == "public":
        copy_doc["accessGroup"] = "public"
        copy_doc["accessNote"] = "Публичная инструкция. Пользователь может открыть её сам."
    else:
        copy_doc["accessGroup"] = "internal"
        copy_doc["accessNote"] = "Внутренняя инструкция. Пользователь может приложить ссылку к заявке, но сам может не иметь доступа."

    return copy_doc


def compact_doc(doc: dict) -> dict:
    return {
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "url": doc.get("url", ""),
        "section": doc.get("section", ""),
        "pathText": doc.get("pathText", ""),
        "text": doc.get("text", ""),
        "keywords": doc.get("keywords", []),
        "accessGroup": doc.get("accessGroup", ""),
        "accessNote": doc.get("accessNote", ""),
    }


def save_csv(path: Path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["status", "accessGroup", "title", "url", "section", "pathText", "textLength", "attachmentsCount"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def save_doc_list_csv(path: Path, docs, access_group: str):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["accessGroup", "title", "url", "section", "pathText", "textLength", "keywords"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for doc in docs:
            writer.writerow({
                "accessGroup": access_group,
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "section": doc.get("section", ""),
                "pathText": doc.get("pathText", ""),
                "textLength": len(doc.get("text", "") or ""),
                "keywords": ", ".join(doc.get("keywords", [])[:30]),
            })


def main():
    print("")
    print("ОБНОВЛЕНИЕ WIKI-БАЗЫ: ПУБЛИЧНЫЕ + ВНУТРЕННИЕ")
    print("=" * 58)
    print("")
    print("Нужны 4 JSON-файла:")
    print("1. старая публичная база, если есть")
    print("2. новая публичная база")
    print("3. старая внутренняя база, если есть")
    print("4. новая внутренняя база")
    print("")
    print("Для первой сборки старые базы можно пропустить, просто нажать Enter.")
    print("Для обычного ежемесячного обновления лучше указывать все 4 файла.")
    print("")

    if len(sys.argv) >= 5:
        old_public_path = clean_path(sys.argv[1]) if sys.argv[1] != "-" else None
        new_public_path = clean_path(sys.argv[2])
        old_internal_path = clean_path(sys.argv[3]) if sys.argv[3] != "-" else None
        new_internal_path = clean_path(sys.argv[4])
    else:
        old_public_path = ask_file("1. Старая публичная база JSON", required=False)
        new_public_path = ask_file("2. Новая публичная база JSON", required=True)
        old_internal_path = ask_file("3. Старая внутренняя база JSON", required=False)
        new_internal_path = ask_file("4. Новая внутренняя база JSON", required=True)

    old_public = load_json_or_js(old_public_path) if old_public_path else []
    new_public = load_json_or_js(new_public_path)
    old_internal = load_json_or_js(old_internal_path) if old_internal_path else []
    new_internal = load_json_or_js(new_internal_path)

    public_diff = diff_docs(old_public, new_public, "public")
    internal_diff = diff_docs(old_internal, new_internal, "internal")

    # Собираем общую новую базу.
    # Если одна и та же страница попала и в публичную, и во внутреннюю базу, публичная версия побеждает.
    combined = []
    seen = set()
    duplicate_internal_in_public = []

    for doc in new_public:
        key = normalize_key(doc)
        if not key or key in seen:
            continue
        combined.append(mark_doc(doc, "public"))
        seen.add(key)

    for doc in new_internal:
        key = normalize_key(doc)
        if not key:
            continue
        if key in seen:
            duplicate_internal_in_public.append(doc)
            continue
        combined.append(mark_doc(doc, "internal"))
        seen.add(key)

    combined.sort(key=lambda d: (d.get("accessGroup", ""), d.get("section", ""), d.get("pathText", ""), d.get("title", "")))

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = new_public_path.parent / f"обновленная_база_wiki_{stamp}"
    out_dir.mkdir(exist_ok=True)

    full_path = out_dir / "база_инструкций_wiki_с_метками_доступа.json"
    min_path = out_dir / "база_инструкций_wiki_для_приложения_с_метками_доступа.min.json"
    js_path = out_dir / "база_инструкций_wiki_с_метками_доступа.js"
    public_changes_csv = out_dir / "изменения_публичные.csv"
    internal_changes_csv = out_dir / "изменения_внутренние.csv"
    added_public_csv = out_dir / "новые_публичные_инструкции.csv"
    added_internal_csv = out_dir / "новые_внутренние_инструкции.csv"
    report_path = out_dir / "отчет_обновления_wiki.txt"

    with full_path.open("w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    compact = [compact_doc(doc) for doc in combined]
    with min_path.open("w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

    with js_path.open("w", encoding="utf-8") as f:
        f.write("window.WIKI_KNOWLEDGE_BASE = ")
        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    save_csv(public_changes_csv, public_diff["rows"])
    save_csv(internal_changes_csv, internal_diff["rows"])
    save_doc_list_csv(added_public_csv, public_diff["added"], "public")
    save_doc_list_csv(added_internal_csv, internal_diff["added"], "internal")

    public_count = sum(1 for doc in combined if doc.get("accessGroup") == "public")
    internal_count = sum(1 for doc in combined if doc.get("accessGroup") == "internal")

    report = f"""ОТЧЁТ ОБНОВЛЕНИЯ WIKI-БАЗЫ
========================================

Дата сборки: {stamp}

ИСТОЧНИКИ
Старая публичная база: {old_public_path if old_public_path else "не указана"}
Новая публичная база: {new_public_path}
Старая внутренняя база: {old_internal_path if old_internal_path else "не указана"}
Новая внутренняя база: {new_internal_path}

ПУБЛИЧНЫЕ ИНСТРУКЦИИ
Старая публичная база: {public_diff["old_count"]}
Новая публичная база: {public_diff["new_count"]}
Добавлено публичных: {len(public_diff["added"])}
Удалено публичных: {len(public_diff["removed"])}
Изменено публичных: {len(public_diff["changed"])}
Без изменений публичных: {len(public_diff["unchanged"])}

ВНУТРЕННИЕ ИНСТРУКЦИИ
Старая внутренняя база: {internal_diff["old_count"]}
Новая внутренняя база: {internal_diff["new_count"]}
Добавлено внутренних: {len(internal_diff["added"])}
Удалено внутренних: {len(internal_diff["removed"])}
Изменено внутренних: {len(internal_diff["changed"])}
Без изменений внутренних: {len(internal_diff["unchanged"])}

ИТОГОВАЯ БАЗА ДЛЯ ПРИЛОЖЕНИЯ
Всего инструкций: {len(combined)}
Публичные: {public_count}
Внутренние: {internal_count}
Внутренних дублей, которые уже есть в публичной базе и были пропущены: {len(duplicate_internal_in_public)}

ФАЙЛЫ РЕЗУЛЬТАТА
- {full_path.name}
- {min_path.name}
- {js_path.name}
- {public_changes_csv.name}
- {internal_changes_csv.name}
- {added_public_csv.name}
- {added_internal_csv.name}

ГЛАВНЫЙ ФАЙЛ ДЛЯ HTML-ПРИЛОЖЕНИЯ
{min_path.name}

ЧТО ДЕЛАТЬ ДАЛЬШЕ
1. Запустить build_wiki_search_app.py.
2. Выбрать текущий HTML приложения.
3. Выбрать файл {min_path.name}.
4. Получить новый HTML, который уже можно отдавать пользователям.
"""

    report_path.write_text(report, encoding="utf-8")

    print("")
    print("ГОТОВО.")
    print(f"Папка с результатом: {out_dir}")
    print("")
    print("Итоговая база:")
    print(f"- всего: {len(combined)}")
    print(f"- публичные: {public_count}")
    print(f"- внутренние: {internal_count}")
    print("")
    print("Главный файл для приложения:")
    print(min_path)
    print("")
    print("Отчёт:")
    print(report_path)
    print("")
    input("Нажми Enter, чтобы закрыть окно...")


if __name__ == "__main__":
    main()
