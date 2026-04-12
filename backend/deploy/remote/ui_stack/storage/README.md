`data/runtime` на сервере хранит:

- `uploads/`
- `logs/`
- `state.json`
- остальные runtime-артефакты backend

Сейчас это persistent host volume для UI-сайта.

Позже сюда же можно добавить:

- отдельные правила cleanup старых uploads;
- snapshot/backup;
- TG runtime в отдельной ветке, если понадобится.
