"""Synchronize published release bodies and README, using this repo's workflow token."""
import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def version(tag):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', tag):
        return None
    return tuple(map(int, tag.removeprefix('v').split('.')))


def table(releases):
    rows = ['| Версия | Дата | Изменения |', '| --- | --- | --- |']
    for release in sorted(releases, key=lambda r: version(r['tag_name']), reverse=True):
        lines = [line.strip().lstrip('#- ').strip() for line in (release.get('body') or '').splitlines()]
        summary = next((s for s in lines if s and not s.startswith('StudyAssistant')), 'Описание не добавлено')
        summary = summary.replace('|', '\\|').replace('<', '&lt;').replace('>', '&gt;')[:180]
        tag = release['tag_name']
        url = 'https://github.com/atroid25/StudyAssistant-releases/releases/tag/' + quote(tag, safe='')
        rows.append(f"| [{tag}]({url}) | {release['published_at'][:10]} | {summary} |")
    return '\n'.join(rows)


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    if repo.lower() != 'atroid25/studyassistant-releases':
        raise ValueError('Run only in the public release repository')
    token = os.environ['GITHUB_TOKEN']
    api = 'https://api.github.com/repos/' + repo
    def call(path, method='GET', payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(api + path, data=data, method=method, headers={
            'Authorization':'Bearer ' + token, 'Accept':'application/vnd.github+json',
            'User-Agent':'StudyAssistant-release-notes', 'Content-Type':'application/json'})
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    releases = []
    page = 1
    while True:
        batch = call(f'/releases?per_page=100&page={page}')
        releases.extend(r for r in batch if not r['draft'] and not r['prerelease'] and version(r['tag_name']))
        if len(batch) < 100:
            break
        page += 1
    for release in releases:
        tag = release['tag_name']
        notes = Path('release-notes') / (tag.removeprefix('v') + '.md')
        if notes.is_file():
            body = notes.read_text(encoding='utf-8').strip()
            if not body:
                raise ValueError('Empty release description: ' + str(notes))
            if (release.get('body') or '').strip() != body:
                call('/releases/' + str(release['id']), 'PATCH', {'body':body})
                release['body'] = body
    readme = call('/contents/README.md?ref=main')
    original = base64.b64decode(readme['content']).decode('utf-8')
    start, end = '<!-- RELEASES:START -->', '<!-- RELEASES:END -->'
    if original.count(start) != 1 or original.count(end) != 1:
        raise ValueError('Missing or duplicate README release markers')
    before, tail = original.split(start)
    _, after = tail.split(end)
    updated = before + start + '\n' + table(releases) + '\n' + end + after
    if updated != original:
        call('/contents/README.md', 'PUT', {'message':'Update published release table', 'sha':readme['sha'],
             'branch':'main', 'content':base64.b64encode(updated.encode('utf-8')).decode('ascii')})
    print(f'Synchronized {len(releases)} published releases')


if __name__ == '__main__':
    main()
