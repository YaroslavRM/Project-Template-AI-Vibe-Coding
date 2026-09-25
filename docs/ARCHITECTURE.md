# Architecture

> Порожній шаблон. Заповнюється через `prompts/02-solution-setup.md`.
> Зміни в цьому файлі — тільки з явного підтвердження власника проєкту.
> Будь-яка зміна = підняти **Версію** + рядок у **Change Log**.

**Версія:** 0.1 (draft)
**Дата:**
**На основі:** FRS v?

---

## 1. Overview

## 2. Requirements Digest

## 3. Architecture Style & Decomposition

## 4. Technology Stack

## 5. Data & Migrations

## 6. API Contracts

## 7. Integrations

## 8. NFR Mapping

| NFR-ID | Вимога | Як реалізовано | Статус |
|---|---|---|---|

## 9. Environments & Delivery

### Local

### Test

### Prod

### Міграції

### Rollback

### Секрети

### Бекапи

## 10. Observability

## 11. Project Structure

> Дерево `source/` + мінімальний набір команд проєкту.
>
> Обов'язково зафіксуй тут **команду локальної перевірки** (тести + лінт + типи
> + UI-тести, якщо є UI) одним рядком — на неї посилається `RulesForAIVibeCoding.md`, розділ
> *Work cycle*, і Definition of Done.
>
> | Дія | Команда |
> |---|---|
> | Встановити залежності | |
> | Запустити локально | |
> | **Локальна перевірка** | |
> | Зібрати | |
> | Задеплоїти на test | |
> | Задеплоїти на prod | |

## 12. Agent Permissions

> Має бути узгоджено з `RulesForAIVibeCoding.md`, розділ *Environments*.

| Дія | Local | Test | Prod |
|---|---|---|---|
| Запуск тестів | вільно | | |
| Деплой | | тільки за командою | тільки за командою |
| Міграції | вільно | тільки за командою | тільки за командою |

## 13. Deferred Decisions

| ID | Рішення | Умова повернутися |
|---|---|---|

## 14. ADR Index

| ADR | Назва | Статус |
|---|---|---|

## 15. Change Log

| Версія | Дата | Що змінилося | Причина / джерело |
|---|---|---|---|
| 0.1 | | Початкова версія | Solution setup (prompt 02) |
