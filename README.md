# lab-index

Каталог учебных работ **dydojopka**. Обновляется полной сверкой репозиториев
через GitHub Actions.

<!-- LAB-INDEX:START -->

## Алгоритмы компьютерной графики

<ul>
  <li><strong>1. Библиотека CreateJS</strong>
    <ol start="4">
      <li><a href="https://github.com/dydojopka/Bubble-pop">Редактор квадратов</a></li>
    </ol>
  </li>
</ul>

## Архитектура ПО

<ul>
  <li><strong>2. Микросервисы</strong>
    <ol start="3">
      <li><a href="https://github.com/dydojopka/SmartCity">Разработка экосистемы микросервисов &quot;Умный город&quot;</a></li>
      <li><a href="https://github.com/dydojopka/SmartCityMonolith">Модульный монолит - объединение двух микросервисов на практике</a></li>
    </ol>
  </li>
</ul>

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
