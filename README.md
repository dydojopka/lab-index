# lab-index

<!-- LAB-INDEX:START -->

## Алгоритмы компьютерной графики

<p>
<strong>1. Библиотека CreateJS</strong><br>
&nbsp;&nbsp;&nbsp;&nbsp;1.4. <a href="https://github.com/dydojopka/Bubble-pop">Редактор квадратов</a>
</p>

## Архитектура ПО

<p>
<strong>2. Микросервисы</strong><br>
&nbsp;&nbsp;&nbsp;&nbsp;2.2. <a href="https://github.com/dydojopka/AshroevE-SoftArch-lab2">Анализ архитектуры</a><br>
&nbsp;&nbsp;&nbsp;&nbsp;2.3. <a href="https://github.com/dydojopka/SmartCity">Разработка экосистемы микросервисов &quot;Умный город&quot;</a><br>
&nbsp;&nbsp;&nbsp;&nbsp;2.4. <a href="https://github.com/dydojopka/SmartCityMonolith">Модульный монолит - объединение двух микросервисов на практике</a>
</p>

## Информационная безопасность

<p>
1. <a href="https://github.com/dydojopka/AshroevE-IS-lab1">Основы криптографии</a><br>
2. <a href="https://github.com/dydojopka/AshroevE-IS-lab2">Статистические методы криптоанализа алфавитных шифров</a><br>
5. <a href="https://github.com/dydojopka/AshroevE-IS-lab5">Метод экспертных оценок</a>
</p>

## Курсовые работы &#40;проекты&#41;

<p>
<strong>1. Разработка веб-приложений</strong><br>
&nbsp;&nbsp;&nbsp;&nbsp;1.1. <a href="https://github.com/dydojopka/Pan.teach">Pan.teach</a><br>
<strong>2. Проектирование информационных систем</strong><br>
&nbsp;&nbsp;&nbsp;&nbsp;2.1. <a href="https://github.com/dydojopka/Local-Stock-Tracker">Веб-приложение для учета локального запаса продуктов</a><br>
&nbsp;&nbsp;&nbsp;&nbsp;2.2. <a href="https://github.com/dydojopka/Local-Stock-Tracker-report">Отчёт</a>
</p>

## Системы ИИ

<p>
1. <a href="https://github.com/dydojopka/AI_systems-lab1">Онтологическое моделирование</a>
</p>

## Учебные практики

<p>
<strong>1. Учебная практика</strong><br>
&nbsp;&nbsp;&nbsp;&nbsp;1.1. <a href="https://github.com/dydojopka/tg-bot-raspmath-isu">Telegram Bot для расписания ИМИТ ИГУ</a><br>
<strong>2. Научно исследовательская практическая работа (2026)</strong><br>
&nbsp;&nbsp;&nbsp;&nbsp;2.1. <a href="https://github.com/dydojopka/simulated-annealing-dnf">Поиск ДНФ методом имитации отжига</a>
</p>

<!-- LAB-INDEX:END -->

---

## Как добавить работу

Одна работа — один собственный репозиторий. Добавьте в корень его **основной
ветки** файл `.lab.yml`, например:

```yaml
course: Архитектура ПО
sections:
  - number: 2
    title: Микросервисы
  - number: 1
    title: Модульный монолит
assignment:
  number: 3
  title: Объединение двух микросервисов на практике
```

Путь идёт от внешнего раздела к внутреннему: здесь это подраздел `2.1`,
задание `3`. Для работы прямо в курсе укажите `sections: []`.
Готовый файл: [`examples/.lab.yml`](examples/.lab.yml).
