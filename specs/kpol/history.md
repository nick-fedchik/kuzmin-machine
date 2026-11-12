# Git-архів пропозицій KPOL v0.1–v0.9

* **Версія:** 0.1.0
* **Дата:** 2026-11-12
* **WI:** [#19](https://github.com/nick-fedchik/kuzmin-machine/issues/19).
* **Статус:** історичні входи, не чинна специфікація.
* **Архівний коміт:** `727c19ecb08a6bd45cffea541a64db01acaab148`.

## Межі та збереження походження

Повні тексти попередніх пропозицій залишаються в Git, а не в поточному
наборі нормативних документів. Нижче — прямі immutable-посилання
на останню спільну базу перед архівуванням; історія й рядки
«Перенесено з» всередині не переписувалися. Версія v0.1 в імені
має редакцію документа 0.1.2; інші — версії 0.2.0–0.9.0.

| Вхід | Повний збережений текст / призначення |
|---|---|
| v0.1 | [kpol-0.1.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.1.0.md) — початкова граматика, референсні приклади й дослідницькі пропозиції. |
| v0.2 | [kpol-0.2.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.2.0.md) — Hazard/Alert, Unknown, Proof. |
| v0.3 | [kpol-0.3.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.3.0.md) — одиниці, Pin, пропозиції часу й нагляду. |
| v0.4 | [kpol-0.4.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.4.0.md) — канали, ownership, CSP. |
| v0.5 | [kpol-0.5.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.5.0.md) — метадані BRAM, C/Verilog, RTM. |
| v0.6 | [kpol-0.6.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.6.0.md) — HMAC/ACL. |
| v0.7 | [kpol-0.7.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.7.0.md) — мутації та фальсифікаційний gate. |
| v0.8 | [kpol-0.8.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.8.0.md) — C-runtime, AXI. |
| v0.9 | [kpol-0.9.0.md](https://github.com/nick-fedchik/kuzmin-machine/blob/727c19ecb08a6bd45cffea541a64db01acaab148/specs/kpol/kpol-0.9.0.md) — тріада, namespace/import, linker. |

Архівування не відкидає ідей і не підтверджує їх. Окремий історичний
[аудит](reviews/kpol-0.2-0.9-audit-review.md) залишається незмінним;
No-Go для повного v1.0 не скасовано.

## Залежності та відтворення

На старих шляхах залишено **лише навігаційні записи** з прямим
посиланням на відповідний повний текст. Тому посилання з історичних
звітів, методик і реєстрів не ведуть у нікуди. Записи не є копіями
дельт або їхніми новими нормативними редакціями. Історичні звіти,
raw, migration mapping і первинні джерела не змінено.

Єдиний знайдений виконуваний споживач тексту дельт —
`SPEC_PATH` у `sw/kpol-ref/tests/test_kpol_reference.py` до цієї зміни.
Три блоки `kpol` v0.1 перенесено без зміни в
[fixtures](../../sw/kpol-ref/tests/fixtures/kpol-v01-examples.md);
цей тест тепер читає fixtures. Пошук залежностей і побайтове порівняння
блоків із Git-оригіналом включено до перевірки PR.

Для отримання повного тексту без мережі:

```bash
git show 727c19ecb08a6bd45cffea541a64db01acaab148:specs/kpol/kpol-0.1.0.md
```

Для старого відтворення необхідно брати **весь старий Git-стан**,
не поєднувати сьогоднішній тест зі старою специфікацією навмання.
Тести поточного frontend не залежать від можливості мережевого
завантаження архіву.

## Історія версій

| Версія | Дата | Зміни |
|---|---|---|
| 0.1.0 | 2026-11-12 | Повні дельти переведено в Git-архів; збережено навігаційні шляхи й окремі тестові приклади (#19). |

## Абревіатури та глосарій

SHA — ідентифікатор Git-коміту; fixture — збережений вхід регресійного
тесту; дельта — попередня пропозиція, що доповнювала іншу редакцію.
