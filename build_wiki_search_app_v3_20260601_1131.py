# -*- coding: utf-8 -*-
r"""
Сборка нового HTML-приложения Wiki-поиска с обновлённой базой.
ВЕРСИЯ 3 (2026-06-01).

Чем v3 отличается от v2 и почему это важно:

ГЛАВНОЕ (фикс «мёртвого приложения»):
  Если в тексте какой-то инструкции встречается фрагмент кода с тегом </script>,
  то при простой вставке базы в HTML браузер считает это концом скрипта. В итоге
  скрипт обрывается, и приложение «умирает»: кнопки не нажимаются, списки не
  открываются. v1 и v2 этот случай не обрабатывали.
  v3 при вставке базы экранирует опасные символы: < > и разделители строк
  U+2028/U+2029. В рабочем приложении они автоматически читаются как обычные
  символы, а браузер уже не видит ложный </script>.

САМОПРОВЕРКА:
  После сборки v3 сам проверяет, что в готовом файле столько же тегов <script> и
  </script>, сколько в исходном. Если появился лишний — печатает ОШИБКУ и не
  выдаёт «ГОТОВО», чтобы сломанный файл не ушёл пользователям.

Также v3 (как и v2):
  - понимает оба формата приложения: const APP = {...} и window.WIKI_KNOWLEDGE_BASE = [...];
  - вырезает объект APP по балансу скобок, а не хрупкой регуляркой;
  - меняет instructions, version, dateDisplay;
  - если структуру не найдёт — НЕ создаёт файл, а честно пишет ошибку.

Как запускать:
    python build_wiki_search_app_v3_20260601_1131.py
или с путями:
    python build_wiki_search_app_v3_20260601_1131.py "текущее.html" "новая_база.min.json"
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

MSK = timezone(timedelta(hours=3))


def clean_path(raw: str) -> Path:
    return Path(raw.strip().strip('"').strip("'")).expanduser()


def ask_file(label: str, extensions=None) -> Path:
    extensions = extensions or []
    while True:
        print("")
        raw = input(label + "\nВставь путь к файлу и нажми Enter: ").strip()
        path = clean_path(raw)
        if path.exists() and path.is_file():
            if extensions and path.suffix.lower() not in extensions:
                print(f"Файл найден, но расширение не похоже на нужное: {path.suffix}")
                print(f"Нужны такие расширения: {', '.join(extensions)}")
                continue
            return path
        print("Не нашла такой файл. Проверь путь и попробуй ещё раз.")


def load_base(path: Path):
    text = path.read_text(encoding="utf-8-sig").strip()
    if text.startswith("window.WIKI_KNOWLEDGE_BASE"):
        text = re.sub(r"^window\.WIKI_KNOWLEDGE_BASE\s*=\s*", "", text).rstrip(";").strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("База должна быть JSON-массивом: [ {...}, {...} ]")
    return data


def safe_html_json(obj) -> str:
    """JSON для безопасной вставки внутрь <script>. Экранирует символы,
    которые иначе ломают HTML-парсер и убивают приложение."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    s = (s.replace("<", "\\u003c")
          .replace(">", "\\u003e")
          .replace("\u2028", "\\u2028")
          .replace("\u2029", "\\u2029"))
    return s


def extract_braced_object(html: str, start_index: int):
    i = start_index
    depth = 0
    in_str = False
    esc = False
    q = ""
    while i < len(html):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == q:
                in_str = False
        else:
            if c in "\"'":
                in_str = True
                q = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return html[start_index:i + 1], start_index, i
        i += 1
    raise ValueError("Не удалось найти закрывающую скобку объекта APP.")


def count_script_tags(text: str):
    return (len(re.findall(r"<script", text, re.I)),
            len(re.findall(r"</script", text, re.I)))


def build():
    print("")
    print("СБОРКА HTML-ПРИЛОЖЕНИЯ С НОВОЙ БАЗОЙ WIKI  (v3)")
    print("=" * 52)
    print("")
    print("Нужно указать:")
    print("1. Текущий HTML-файл приложения.")
    print("2. Новый JSON с базой инструкций, лучше файл:")
    print("   база_инструкций_wiki_для_приложения_с_метками_доступа.min.json")
    print("")

    if len(sys.argv) >= 3:
        html_path = clean_path(sys.argv[1])
        json_path = clean_path(sys.argv[2])
    else:
        html_path = ask_file("1. Текущий HTML приложения", extensions=[".html", ".htm"])
        json_path = ask_file("2. Новый JSON с базой", extensions=[".json", ".js"])

    html = html_path.read_text(encoding="utf-8")
    src_open, src_close = count_script_tags(html)
    data = load_base(json_path)

    for item in data:
        if isinstance(item, dict):
            item.setdefault("source", "Wiki")

    total = len(data)
    public_count = sum(1 for x in data if x.get("accessGroup") == "public")
    internal_count = sum(1 for x in data if x.get("accessGroup") == "internal")

    print("")
    print("База прочитана:")
    print(f"- всего инструкций: {total}")
    print(f"- публичные: {public_count}")
    print(f"- внутренние: {internal_count}")

    version = input("\nВерсия нового HTML, например v0.27. Если оставить пусто, оставлю как есть: ").strip()

    now = datetime.now(MSK)
    stamp = now.strftime("%Y%m%d_%H%M")
    disp = now.strftime("%d.%m.%Y %H:%M") + " МСК"

    new_html = None
    mode = None
    version_for_name = version or "v_new"

    m_app = re.search(r"const\s+APP\s*=\s*", html)
    if m_app:
        obj_text, o_start, o_end = extract_braced_object(html, m_app.end())
        app = json.loads(obj_text)
        if "instructions" not in app:
            raise ValueError("В объекте APP нет ключа instructions — структура изменилась.")
        app["instructions"] = data
        if version:
            app["version"] = version
        app["dateDisplay"] = disp
        new_html = html[:o_start] + safe_html_json(app) + html[o_end + 1:]
        mode = "const APP"
        version_for_name = app.get("version", version or "v_new")

    if new_html is None:
        m_kb = re.search(r"window\.WIKI_KNOWLEDGE_BASE\s*=\s*", html)
        if not m_kb:
            print("\nОШИБКА: не нашла ни const APP = {...}, ни window.WIKI_KNOWLEDGE_BASE.")
            print("Структура HTML отличается от ожидаемой. Файл не создан.")
            input("Нажми Enter, чтобы закрыть окно...")
            return
        # для массива [...] вырезаем по балансу квадратных скобок
        i = m_kb.end()
        depth = 0; in_str = False; esc = False; q = ""; arr_start = i
        while i < len(html):
            c = html[i]
            if in_str:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == q: in_str = False
            else:
                if c in "\"'": in_str = True; q = c
                elif c == "[": depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        new_html = html[:arr_start] + safe_html_json(data) + html[i + 1:]
        mode = "window.WIKI_KNOWLEDGE_BASE"

    # ---- САМОПРОВЕРКА: не появился ли лишний </script> ----
    out_open, out_close = count_script_tags(new_html)
    if out_open != src_open or out_close != src_close:
        print("\n!!! ОШИБКА САМОПРОВЕРКИ !!!")
        print(f"В исходном файле было <script>={src_open}, </script>={src_close}.")
        print(f"В собранном стало    <script>={out_open}, </script>={out_close}.")
        print("Это значит, что в базе есть текст, ломающий скрипт, и он не экранировался.")
        print("Файл НЕ сохранён, чтобы сломанная версия не ушла пользователям.")
        print("Сообщите разработчику этот текст ошибки.")
        input("Нажми Enter, чтобы закрыть окно...")
        return

    safe_version = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9_.\-]+", "_", str(version_for_name))
    out_name = f"Заявка_в_IT_отдел_{safe_version}_{stamp}.html"
    out_path = html_path.parent / out_name
    out_path.write_text(new_html, encoding="utf-8")

    report_path = html_path.parent / f"отчет_сборки_HTML_{safe_version}_{stamp}.txt"
    report_path.write_text(
        "ОТЧЁТ СБОРКИ HTML-ПРИЛОЖЕНИЯ WIKI (v3)\n"
        "======================================\n\n"
        f"Формат базы в HTML: {mode}\n"
        f"Шаблон HTML: {html_path}\n"
        f"База JSON: {json_path}\n"
        f"Версия: {version_for_name}\n"
        f"Дата сборки: {disp}\n\n"
        f"Всего инструкций: {total}\n"
        f"Публичные: {public_count}\n"
        f"Внутренние: {internal_count}\n\n"
        f"Самопроверка script-тегов: <script>={out_open}, </script>={out_close} (как в исходнике) — ОК\n"
        f"Новый HTML: {out_path.name}\n",
        encoding="utf-8",
    )

    print("")
    print(f"ГОТОВО. Формат базы: {mode}. База заменена на {total} инструкций.")
    print(f"Самопроверка script-тегов пройдена (<script>={out_open}, </script>={out_close}).")
    print("Новый HTML создан:")
    print(out_path)
    print("")
    print("ОБЯЗАТЕЛЬНО: открой готовый файл и проверь, что списки открываются и кнопки нажимаются.")
    print("Если приложение «зависло» — пользователям не отдавать.")
    print("")
    input("Нажми Enter, чтобы закрыть окно...")


if __name__ == "__main__":
    build()
