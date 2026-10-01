# Tech Context
Браузер + локальный Python для скриптов Wiki. Запуск: открыть `index.html`. `vercel.json` — раздача одной ссылкой (чтобы у пользователей не оседали старые копии).

## Команды на сервере (проверенные; писать владелице блоком `# 1. …`, см. CLAUDE.md п. 7)

Сервер: root@8314715-nw871204 (Timeweb). Здесь фиксируем реальные пути репозитория, имя службы, пользователя, логи и команды деплоя/диагностики этого проекта. Вносить только то, что подтверждено успешным выводом или взято из `deploy/`; на каждый новый путь или команду, которые оказались верными, — сразу запись сюда. Секреты не записывать.

Опубликовано на сервере: **https://meotida.salamashkina.ru/zayavka-old/** («Заявка в IT отдел» v0.29) — nginx + сертификат Let's Encrypt. Настраивает всё скрипт `deploy/publish-sites.sh` в репозитории `meotida_2` (таблица путей и факты сервера — в его `memory-bank/techContext.md`). На сервере: страница `/var/www/apps/zayavka-old/index.html`, код — `/opt/sites-src/meotida`. Проверено владелицей 2026-10-01: ответ 200, повторный запуск скрипта тоже.

Обновить сайт после изменений в `main` этого репозитория (проверено):

```bash
# 1. Забрать скрипт публикации с main и запустить: подтянет свежий main и скопирует index.html
curl -fsSL https://raw.githubusercontent.com/Salamashko/meotida_2/main/deploy/publish-sites.sh -o /root/publish-sites.sh   # ожидается: без ошибок
bash /root/publish-sites.sh   # ожидается: в конце https://meotida.salamashkina.ru/zayavka-old/ → 200
# 2. Проверить
curl -sI https://meotida.salamashkina.ru/zayavka-old/ | head -3   # ожидается: HTTP/1.1 200 OK
```
Vercel остаётся запасным вариантом (в РФ часто недоступен из-за РКН).
