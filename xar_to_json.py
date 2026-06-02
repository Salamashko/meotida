# -*- coding: utf-8 -*-
r"""
XWiki/XAR -> JSON база инструкций для HTML-приложения

Что делает:
1. Берёт файл Export_Wiki.xar или другой .xar/.zip экспорт XWiki.
2. Достаёт из него страницы-инструкции.
3. Не вытаскивает картинки в JSON, чтобы база не была огромной.
4. Создаёт:
   - база_инструкций_wiki.json
   - база_инструкций_wiki_для_приложения.min.json
   - база_инструкций_wiki.js
   - список_инструкций.csv
   - отчет.txt

Как запускать:
1. Положите этот файл рядом с Export_Wiki.xar.
2. Откройте эту папку в командной строке.
3. Выполните:
   python xar_to_json.py

Если файл экспорта называется иначе:
   python xar_to_json.py "C:\путь\к\файлу\Export_Wiki.xar"
"""

import csv
import html
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from xml.etree.ElementTree import iterparse


# =========================
# НАСТРОЙКИ. МОЖНО НЕ ТРОГАТЬ
# =========================

BASE_VIEW_URL = "https://wiki.gkmillenium.ru/bin/view/"

# Эти разделы обычно служебные. Их не берём в базу инструкций.
EXCLUDE_FIRST_SPACES = {
    "XWiki",
    "xwiki",
    "Help",
    "Main",
    "Menu",
    "Panels",
    "Macros",
    "Ideas",
    "Sandbox",
}

# Если оставить список пустым, скрипт возьмёт все разделы, кроме служебных.
# Если нужно брать только конкретные разделы, впишите их сюда.
# Пример:
# INCLUDE_FIRST_SPACES_ONLY = {"polzovatelskaya-dokumentaciya-filialy"}
INCLUDE_FIRST_SPACES_ONLY = set()

# Минимальная длина текста инструкции. Очень короткие страницы часто бывают пустыми разделами.
MIN_TEXT_LENGTH = 40

# Сколько ключевых слов сохранить для каждой инструкции.
KEYWORDS_LIMIT = 35


STOPWORDS = {
    "и", "в", "во", "на", "не", "что", "как", "к", "ко", "по", "для", "из", "за", "от", "до",
    "или", "если", "то", "это", "при", "над", "под", "надо", "нужно", "будет", "можно",
    "так", "же", "а", "но", "мы", "вы", "он", "она", "они", "его", "ее", "её", "их",
    "с", "со", "у", "о", "об", "обо", "без", "через", "после", "перед", "между",
    "где", "когда", "тут", "там", "далее", "затем", "далее", "ниже", "выше",
    "данные", "данных", "документ", "документа", "документы", "файл", "файла",
    "страница", "страницы", "инструкция", "инструкции", "пользователь", "пользователя",
    "the", "and", "or", "in", "on", "for", "of", "to", "from", "with", "by",
}


def local_name(tag: str) -> str:
    """Убирает namespace из XML-тега."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def split_xwiki_space(web: str):
    """
    XWiki разделяет вложенные пространства точками.
    Но точка может быть экранирована как \\. внутри названия.
    """
    if not web:
        return []

    result = []
    current = []
    escaped = False

    for ch in web:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ".":
            result.append("".join(current))
            current = []
        else:
            current.append(ch)

    result.append("".join(current))
    return [part for part in result if part]


def build_view_url(web: str, name: str) -> str:
    """Собирает ссылку на страницу в XWiki."""
    parts = split_xwiki_space(web)

    if name and name != "WebHome":
        parts.append(name)

    encoded = "/".join(quote(part, safe="-_.~") for part in parts)

    if not encoded.endswith("/"):
        encoded += "/"

    return BASE_VIEW_URL + encoded


def clean_xwiki_text(text: str) -> str:
    """Очень мягкая очистка XWiki-разметки до обычного текста."""
    if not text:
        return ""

    text = html.unescape(text)

    # Убираем служебные macro-блоки, но текст внутри полностью не анализируем.
    text = re.sub(r"\{\{/?(?:html|toc|box|code|warning|info|success|error|velocity|groovy|display)[^}]*\}\}", " ", text, flags=re.I)

    # Картинки оставляем как упоминание файла, а не base64.
    text = re.sub(r"!\s*image:([^!\n]+)!", r" [картинка: \1] ", text)
    text = re.sub(r"image:([^\s\]\)]+)", r" [картинка: \1] ", text)

    # Ссылки XWiki: [[текст>>ссылка]] -> текст ссылка
    text = re.sub(r"\[\[([^>\]]+?)>>([^\]]+?)\]\]", r"\1 \2", text)

    # Ссылки XWiki: [[текст]] -> текст
    text = re.sub(r"\[\[([^\]]+?)\]\]", r"\1", text)

    # Заголовки вида == Заголовок ==
    text = re.sub(r"(?m)^\s*=+\s*(.*?)\s*=+\s*$", r"\1", text)

    # Жирный/курсив XWiki.
    text = text.replace("**", "")
    text = text.replace("//", "")

    # Маркеры списков.
    text = re.sub(r"(?m)^\s*[\*\#]+\s*", "- ", text)

    # Остатки фигурных макросов.
    text = re.sub(r"\{\{[^}\n]{1,80}\}\}", " ", text)

    # Много пробелов и пустых строк.
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def make_fallback_title(web: str, name: str) -> str:
    parts = split_xwiki_space(web)
    if name and name != "WebHome":
        raw = name
    elif parts:
        raw = parts[-1]
    else:
        raw = "Без названия"

    raw = raw.replace("\\.", ".")
    raw = raw.replace("-", " ")
    raw = raw.replace("_", " ")
    return raw.strip() or "Без названия"


def make_keywords(title: str, path_text: str, content: str):
    source = f"{title} {path_text} {content}".lower()
    words = re.findall(r"[a-zа-яё0-9][a-zа-яё0-9._-]{1,}", source, flags=re.I)

    normalized = []
    for word in words:
        word = word.strip("._-").lower()
        if len(word) < 2:
            continue
        if word in STOPWORDS:
            continue
        if word.isdigit():
            continue
        normalized.append(word)

    counts = Counter(normalized)
    return [word for word, _ in counts.most_common(KEYWORDS_LIMIT)]


def parse_xwiki_xml_from_zip(zip_file, zip_info):
    """
    Парсит один XML-документ из XAR.
    Важно: attachment/content с base64 не сохраняем.
    """
    fields = {}
    attachments = []

    stack = []

    try:
        with zip_file.open(zip_info) as file_obj:
            context = iterparse(file_obj, events=("start", "end"))

            for event, elem in context:
                tag = local_name(elem.tag)

                if event == "start":
                    stack.append(tag)
                    continue

                # event == "end"
                text = elem.text or ""

                # Берём только прямые поля документа:
                # <xwikidoc><web>...</web></xwikidoc>
                # <xwikidoc><content>...</content></xwikidoc>
                if len(stack) >= 2 and stack[-2] == "xwikidoc":
                    if tag in {
                        "web",
                        "name",
                        "title",
                        "content",
                        "author",
                        "creator",
                        "version",
                        "date",
                        "creationDate",
                        "contentUpdateDate",
                        "language",
                    }:
                        fields[tag] = text

                # Внутри attachment берём только имя файла, не base64.
                if tag == "filename" and "attachment" in stack:
                    filename = text.strip()
                    if filename:
                        attachments.append(filename)

                # Чистим крупные узлы, чтобы память не пухла на большом XAR.
                if tag in {"attachment", "object", "class"}:
                    elem.clear()
                elif tag in {"content"} and "attachment" in stack:
                    elem.clear()
                else:
                    elem.clear()

                if stack:
                    stack.pop()

    except Exception as exc:
        return None, f"{zip_info.filename}: ошибка чтения XML: {exc}"

    if not fields.get("web") or not fields.get("name"):
        return None, None

    web = fields.get("web", "").strip()
    name = fields.get("name", "").strip()
    title = (fields.get("title") or "").strip() or make_fallback_title(web, name)
    raw_content = fields.get("content", "") or ""
    plain_content = clean_xwiki_text(raw_content)

    first_space = split_xwiki_space(web)[0] if split_xwiki_space(web) else ""

    if INCLUDE_FIRST_SPACES_ONLY and first_space not in INCLUDE_FIRST_SPACES_ONLY:
        return None, None

    if first_space in EXCLUDE_FIRST_SPACES:
        return None, None

    if len(plain_content) < MIN_TEXT_LENGTH:
        return None, None

    path_parts = split_xwiki_space(web)
    url = build_view_url(web, name)

    page_id_source = f"{web}.{name}".strip(".")
    page_id = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9_.-]+", "_", page_id_source)

    doc = {
        "id": page_id,
        "title": title,
        "url": url,
        "wiki": "xwiki",
        "web": web,
        "name": name,
        "section": first_space,
        "path": path_parts,
        "pathText": " / ".join(path_parts),
        "version": fields.get("version", "").strip(),
        "author": fields.get("author", "").strip(),
        "creator": fields.get("creator", "").strip(),
        "date": fields.get("date", "").strip(),
        "contentUpdateDate": fields.get("contentUpdateDate", "").strip(),
        "text": plain_content,
        "keywords": make_keywords(title, " ".join(path_parts), plain_content),
        "attachments": sorted(set(attachments)),
        "attachmentsCount": len(set(attachments)),
        "sourceFile": zip_info.filename,
    }

    return doc, None


def find_archive_from_args_or_folder():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser()
        if path.exists():
            return path
        print(f"Не нашла файл: {path}")
        sys.exit(1)

    candidates = list(Path.cwd().glob("*.xar")) + list(Path.cwd().glob("*.zip"))
    candidates = [p for p in candidates if p.is_file()]

    if not candidates:
        print("В этой папке нет .xar или .zip файла.")
        print("Положи скрипт рядом с Export_Wiki.xar и запусти ещё раз.")
        sys.exit(1)

    if len(candidates) == 1:
        return candidates[0]

    print("Нашла несколько архивов. Выбери номер:")
    for i, path in enumerate(candidates, start=1):
        print(f"{i}. {path.name}")

    while True:
        choice = input("Номер файла: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        print("Напиши только номер из списка.")


def save_results(archive_path: Path, docs, errors):
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = archive_path.parent / f"база_из_wiki_{stamp}"
    out_dir.mkdir(exist_ok=True)

    full_json_path = out_dir / "база_инструкций_wiki.json"
    min_json_path = out_dir / "база_инструкций_wiki_для_приложения.min.json"
    js_path = out_dir / "база_инструкций_wiki.js"
    csv_path = out_dir / "список_инструкций.csv"
    report_path = out_dir / "отчет.txt"

    docs_sorted = sorted(docs, key=lambda d: (d.get("section", ""), d.get("pathText", ""), d.get("title", "")))

    with full_json_path.open("w", encoding="utf-8") as f:
        json.dump(docs_sorted, f, ensure_ascii=False, indent=2)

    # Компактная версия для вставки/загрузки в HTML-приложение.
    compact_docs = [
        {
            "id": d["id"],
            "title": d["title"],
            "url": d["url"],
            "section": d["section"],
            "pathText": d["pathText"],
            "text": d["text"],
            "keywords": d["keywords"],
        }
        for d in docs_sorted
    ]

    with min_json_path.open("w", encoding="utf-8") as f:
        json.dump(compact_docs, f, ensure_ascii=False, separators=(",", ":"))

    with js_path.open("w", encoding="utf-8") as f:
        f.write("window.WIKI_KNOWLEDGE_BASE = ")
        json.dump(compact_docs, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "title",
            "url",
            "section",
            "pathText",
            "textLength",
            "keywords",
            "attachmentsCount",
            "sourceFile",
        ])
        for d in docs_sorted:
            writer.writerow([
                d["title"],
                d["url"],
                d["section"],
                d["pathText"],
                len(d["text"]),
                ", ".join(d["keywords"]),
                d["attachmentsCount"],
                d["sourceFile"],
            ])

    sections = Counter(d.get("section", "") for d in docs_sorted)

    with report_path.open("w", encoding="utf-8") as f:
        f.write("ОТЧЁТ ПО ВЫГРУЗКЕ XWIKI/XAR\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Исходный файл: {archive_path}\n")
        f.write(f"Найдено инструкций: {len(docs_sorted)}\n")
        f.write(f"Ошибок чтения XML: {len(errors)}\n\n")
        f.write("Разделы:\n")
        for section, count in sections.most_common():
            f.write(f"- {section}: {count}\n")

        if errors:
            f.write("\nОшибки:\n")
            for error in errors[:100]:
                f.write(f"- {error}\n")
            if len(errors) > 100:
                f.write(f"... и ещё {len(errors) - 100} ошибок\n")

        f.write("\nФайлы результата:\n")
        f.write(f"- {full_json_path.name}\n")
        f.write(f"- {min_json_path.name}\n")
        f.write(f"- {js_path.name}\n")
        f.write(f"- {csv_path.name}\n")

    return out_dir, full_json_path, min_json_path, js_path, csv_path, report_path


def main():
    archive_path = find_archive_from_args_or_folder()

    print("")
    print("Начинаю разбор архива.")
    print(f"Файл: {archive_path}")
    print("Это может занять несколько минут. Не закрывай окно.")
    print("")

    docs = []
    errors = []

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            xml_files = [
                info for info in zf.infolist()
                if info.filename.lower().endswith(".xml")
                and not info.filename.lower().endswith("package.xml")
                and not info.is_dir()
            ]

            total = len(xml_files)
            print(f"XML-файлов внутри: {total}")

            for index, info in enumerate(xml_files, start=1):
                if index % 50 == 0 or index == total:
                    print(f"Обработано: {index}/{total}")

                doc, error = parse_xwiki_xml_from_zip(zf, info)

                if error:
                    errors.append(error)

                if doc:
                    docs.append(doc)

    except zipfile.BadZipFile:
        print("Ошибка: файл не похож на ZIP/XAR архив.")
        print("Проверь, что файл не повреждён и скачался полностью.")
        sys.exit(1)

    out = save_results(archive_path, docs, errors)
    out_dir, full_json_path, min_json_path, js_path, csv_path, report_path = out

    print("")
    print("ГОТОВО.")
    print(f"Папка с результатом: {out_dir}")
    print("")
    print("Главные файлы:")
    print(f"1. {min_json_path.name} — для HTML-приложения")
    print(f"2. {full_json_path.name} — полная JSON-база")
    print(f"3. {csv_path.name} — список инструкций для проверки в Excel")
    print(f"4. {report_path.name} — отчёт")
    print("")
    print("Теперь можно прислать сюда файл:")
    print(min_json_path)
    print("")
    input("Нажми Enter, чтобы закрыть окно...")


if __name__ == "__main__":
    main()
