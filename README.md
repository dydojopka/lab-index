# lab-index

Каталог учебных работ **dydojopka**. Обновляется полной сверкой репозиториев
через GitHub Actions.

<!-- LAB-INDEX:START -->

## Алгоритмы компьютерной графики

<p>
<strong>1. Библиотека CreateJS</strong><br>
&nbsp;&nbsp;&nbsp;1.4. <a href="https://github.com/dydojopka/Bubble-pop">Редактор квадратов</a>
</p>

## Архитектура ПО

<p>
<strong>2. Микросервисы</strong><br>
&nbsp;&nbsp;&nbsp;2.3. <a href="https://github.com/dydojopka/SmartCity">Разработка экосистемы микросервисов &quot;Умный город&quot;</a><br>
&nbsp;&nbsp;&nbsp;2.4. <a href="https://github.com/dydojopka/SmartCityMonolith">Модульный монолит - объединение двух микросервисов на практике</a>
</p>

<!-- LAB-INDEX:END -->

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
