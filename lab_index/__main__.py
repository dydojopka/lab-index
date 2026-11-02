"""The only orchestration path: read everything, validate everything, then write."""

import argparse
import os
import sys

from . import LabIndexError
from .catalog import Work, build_catalog
from .github import GitHub, MAX_README, target_name
from .metadata import parse_metadata
from .readme import block_bounds, render_catalog, replace_block


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Полная сверка учебных работ dydojopka')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true', help='проверить, ничего не записывая')
    modes.add_argument('--publish', action='store_true', help='условно обновить README через API')
    args = parser.parse_args(argv)
    mode = 'publish' if args.publish else 'check'
    checked = included = 0
    secrets = [os.environ.get(name, '') for name in ('LABS_READ_TOKEN', 'INDEX_WRITE_TOKEN')]

    def report(message, *, error=False):
        for secret in secrets:
            if secret:
                message = message.replace(secret, '[REDACTED]')
        print(f'Режим: {mode}; проверено: {checked}; включено: {included}; {message}',
              file=sys.stderr if error else sys.stdout)

    try:
        required = ['LABS_READ_TOKEN', 'GITHUB_REPOSITORY']
        if args.publish:
            required.append('INDEX_WRITE_TOKEN')
        for name in required:
            if not os.environ.get(name):
                raise LabIndexError(f'не задана переменная {name}')
        name = target_name(os.environ['GITHUB_REPOSITORY'])
        reader = GitHub(secrets[0])
        writer = GitHub(secrets[1]) if args.publish else None
        reader.verify_owner()
        target = reader.repository(name)
        original = reader.file(target, 'README.md')
        block_bounds(original.content)
        works = []
        for repo in reader.repositories():
            data = reader.file(repo, '.lab.yml')
            checked += 1
            if data is not None:
                included += 1
                try:
                    metadata = parse_metadata(data.content)
                except LabIndexError as error:
                    raise LabIndexError(f'{repo.name}: .lab.yml: {error}') from None
                works.append(Work(repo, metadata))
        content = replace_block(original.content, render_catalog(build_catalog(works)))
        if len(content) > MAX_README:
            raise LabIndexError('README.md: результат больше 1 МиБ')
        if content == original.content:
            report('без изменений; проверка успешна')
        elif writer is None:
            report('требуется изменение; проверка успешна, запись не выполнялась')
        else:
            writer.publish(target, original, content)
            report('опубликовано; проверка успешна')
        return 0
    except LabIndexError as error:
        report(f'ошибка: {error}', error=True)
        return 1
    except Exception:
        # Unexpected failures must not dump request objects, secrets or YAML.
        report('ошибка: внутренняя ошибка; публикация не подтверждена', error=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
