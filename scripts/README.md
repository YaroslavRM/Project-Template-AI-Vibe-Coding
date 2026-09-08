# scripts/

| Файл | Призначення |
|---|---|
| `check-template.py` | enforcement-файли не змінені + структура на місці + хуки увімкнені |
| `check-ids.py` | traceability за ID: ніщо не посилається на вимогу, якої немає у FRS |
| `check-slice.py` | механічна частина Definition of Done для одного зрізу |
| `integrity.sha256` | пінені хеші всіх enforcement-файлів |

```bash
python3 scripts/check-template.py                              # перевірити
python3 scripts/check-ids.py                                   # traceability
python3 scripts/check-slice.py SLICE-014                       # DoD зрізу
python3 scripts/check-template.py --fix --i-know-what-im-doing # оновити baseline
```

`check-template.py` і `check-ids.py` запускаються автоматично з
`.githooks/pre-commit`. Усі три потребують лише Python 3, без залежностей.

## Маніфест

`integrity.sha256` пінить не тільки правила, а й механізм, який їх виконує:
три скрипти, обидва git-хуки, обидва хуки агента і `settings.json`.
Пінити самі правила недостатньо — перевірка, переписана на `print("OK")`,
проходить і pre-commit, і CI.

Сам маніфест покрити маніфестом не можна — вийде коло. Його хеш зашитий
окремо в `.github/workflows/template-check.yml`, який з тієї ж причини
у маніфест не входить: ланцюг workflow → маніфест → решта, без циклу. Щоб протягнути змінену
перевірку повз CI, треба змінити два файли в різних місцях, і це видно.

## `--fix`

Свідома дія, і навмисно незручна: потрібен другий прапорець
`--i-know-what-im-doing` **і** термінал. Причина конкретна — заборона в
`settings.json` збігається з текстом команди, тож обходиться перестановкою
(`python3 ./scripts/check-template.py --fix`). Термінал переписати не можна.

Якщо `integrity.sha256` зник, скрипт не перебудовує baseline мовчки, а падає:
інакше зміну правил можна було б «узаконити» видаленням одного файлу.

Хеш не збігається, а нічого ви не чіпали — перевірте CRLF (див.
`.gitattributes`), перш ніж тягнутися до `--fix`.

## Список REQUIRED

Дзеркалить розділ *Project structure* правил. Додали файл у структуру —
додайте і туди, інакше скелет мовчки недорахується частини.
