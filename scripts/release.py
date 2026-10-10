"""Package one CI run's binaries and publish reviewed release-candidate tags."""

import argparse
import hashlib
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


REPOSITORY = 'kodxana/lbry-sdk-ng'
HUB_REPOSITORY = 'kodxana/lbry-hub-ng'
VERSION = r'\d+\.\d+\.\d+(?:rc[1-9]\d*)?'
CI_REPORTS = {
    'ci-linux-' + suite for suite in
    ('lint', 'unit', 'blockchain', 'claims', 'datanetwork', 'other', 'takeovers', 'transactions', 'build')
} | {'ci-windows', 'ci-macos'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def prepare(source, artifacts, output, repository, commit, run_id):
    version_match = re.search(r'^__version__ = "(' + VERSION + r')"$',
                              (source / 'lbry/__init__.py').read_text(), re.M)
    if not version_match or not re.fullmatch(r'[a-f0-9]{40}', commit) or not run_id.isdigit():
        raise ValueError('Invalid package version, source commit or workflow run ID')
    version = version_match[1]
    hub = re.search(r'hub@git\+https://github.com/kodxana/lbry-hub-ng.git@([a-f0-9]{40})[\'"\s]',
                    (source / 'setup.py').read_text())
    if not hub:
        raise ValueError('The Hub dependency must be pinned to a full commit SHA')
    notes_path = source / 'docs/releases' / (version + '.md')
    notes = notes_path.read_text(encoding='utf-8')
    required = CI_REPORTS | {'lbrynet-linux', 'lbrynet-windows', 'lbrynet-macos'}
    if {p.name for p in artifacts.iterdir()} != required:
        raise ValueError('Expected the three binaries and all CI reports from one run')
    if any(p.is_symlink() for p in artifacts.rglob('*')):
        raise ValueError('Artifact files must not be symbolic links')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Release output directory must be empty')
    assets = []
    for platform in ('linux', 'windows', 'macos'):
        suffix = '.exe' if platform == 'windows' else ''
        directory = artifacts / ('lbrynet-' + platform)
        binary = directory / ('lbrynet' + suffix)
        if list(directory.iterdir()) != [binary] or not binary.is_file() or binary.stat().st_size == 0:
            raise ValueError(f'Expected exactly one nonempty {platform} executable')
        target = output / f'lbrynet-{version}-{platform}-x86_64{suffix}'
        shutil.copyfile(binary, target)
        if platform != 'windows':
            target.chmod(0o755)
        assets.append(target)
    validation = output / f'validation-{version}.zip'
    with zipfile.ZipFile(validation, 'w', zipfile.ZIP_DEFLATED) as archive:
        for report in sorted(CI_REPORTS):
            directory = artifacts / report
            files = sorted(p for p in directory.rglob('*') if p.is_file())
            if not any(p.suffix == '.log' for p in files) or not (directory / 'packages.txt').is_file():
                raise ValueError(f'Missing logs or package inventory: {report}')
            for path in files:
                archive.write(path, path.relative_to(artifacts).as_posix())
    assets.append(validation)
    provenance = output / 'provenance.json'
    write_json(provenance, {
        'repository': repository, 'version': version, 'commit': commit, 'run_id': run_id,
        'workflow_url': f'https://github.com/{repository}/actions/runs/{run_id}',
        'hub_repository': HUB_REPOSITORY, 'hub_commit': hub[1],
        'binaries': {p.name: sha256(p) for p in assets if p.name.startswith('lbrynet-')},
    })
    assets.append(provenance)
    checksums = output / 'SHA256SUMS'
    checksums.write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(assets)), encoding='utf-8')
    assets.append(checksums)
    notes_url = f'https://github.com/{repository}/blob/{commit}/docs/releases/{version}.md'
    notes = re.sub(r'\]\((\.[^)]+)\)', lambda m: '](' + urllib.parse.urljoin(notes_url, m[1]) + ')', notes)
    notes += (
        '\n## Downloads\n\n'
        'Choose the `lbrynet` executable for Windows x64, Linux x86-64 or Intel macOS 15+. '
        'The executables include Python. The Linux binary requires glibc 2.36 or newer. '
        'Apple Silicon and musl are not release targets.\n\n'
        'Verify downloads with `SHA256SUMS`. On Linux/macOS, grant the file executable '
        'permission with `chmod +x <filename>`. These binaries are unsigned; macOS is not notarized. '
        'Keep separate wallet backups and the previous environment when trying a candidate.\n\n'
        f'Built from `{commit}` in [CI run {run_id}]'
        f'(https://github.com/{repository}/actions/runs/{run_id}). '
        f'`validation-{version}.zip` preserves the test/build logs and dependency inventories. '
        '`provenance.json` records the source revisions and binary hashes.\n'
    )
    (output / 'RELEASE_NOTES.md').write_text(notes, encoding='utf-8')
    write_json(output / 'manifest.json', {
        'repository': repository, 'version': version, 'commit': commit, 'run_id': run_id,
        'hub_commit': hub[1], 'notes_sha256': sha256(output / 'RELEASE_NOTES.md'),
        'assets': [dict(name=p.name, size=p.stat().st_size, sha256=sha256(p)) for p in assets],
    })


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, body=None, file=None):
        host = 'uploads.github.com' if file else 'api.github.com'
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28'}
        data = None
        if file:
            data = file.read_bytes()
            headers['Content-Type'] = 'application/octet-stream'
        elif body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request('https://' + host + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)


def require_merged(api, repository, commit):
    comparison = api.request('GET', f'/repos/{repository}/compare/{commit}...master')
    if comparison['merge_base_commit']['sha'] != commit:
        raise ValueError(f'{repository} revision is not merged into master')


def require_tag(api, version, commit):
    base = f'/repos/{REPOSITORY}'
    reference = api.request('GET', f'{base}/git/ref/tags/v{version}')['object']
    while reference['type'] == 'tag':
        reference = api.request('GET', f'{base}/git/tags/{reference["sha"]}')['object']
    if reference['type'] != 'commit' or reference['sha'] != commit:
        raise ValueError('Release tag no longer points to the tested commit')


def hub_checks(api, commit):
    require_merged(api, HUB_REPOSITORY, commit)
    urls = []
    for workflow in ('build.yml', 'codeql-analysis.yml'):
        runs = api.request('GET', f'/repos/{HUB_REPOSITORY}/actions/workflows/{workflow}/runs'
                           f'?head_sha={commit}&status=success&per_page=100')['workflow_runs']
        if not runs:
            raise ValueError(f'The pinned Hub revision has no successful {workflow} run')
        run = runs[0]
        jobs = api.request('GET', f'/repos/{HUB_REPOSITORY}/actions/runs/{run["id"]}/jobs?per_page=100')
        if (run['head_sha'] != commit or not jobs['jobs'] or
                jobs['total_count'] != len(jobs['jobs']) or
                any(j['conclusion'] != 'success' for j in jobs['jobs'])):
            raise ValueError(f'The pinned Hub revision has incomplete {workflow} checks')
        urls.append(run['html_url'])
    return urls


def validate_bundle(directory, env):
    manifest = json.loads((directory / 'manifest.json').read_text())
    version = manifest['version']
    expected_context = {
        'GITHUB_REPOSITORY': REPOSITORY, 'GITHUB_REF': 'refs/tags/v' + version,
        'GITHUB_SHA': manifest['commit'], 'GITHUB_RUN_ID': manifest['run_id'],
    }
    if (manifest['repository'] != REPOSITORY or env.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch') or
            not re.fullmatch(r'\d+\.\d+\.\d+rc[1-9]\d*', version) or
            any(env.get(key) != value for key, value in expected_context.items())):
        raise ValueError('Publication requires a matching release-candidate tag in the community repository')
    expected = {f'lbrynet-{version}-{platform}-x86_64' + ('.exe' if platform == 'windows' else '')
                for platform in ('linux', 'windows', 'macos')}
    expected |= {f'validation-{version}.zip', 'provenance.json', 'SHA256SUMS'}
    assets = manifest['assets']
    if {a['name'] for a in assets} != expected or len(assets) != len(expected):
        raise ValueError('Unexpected release asset list')
    for asset in assets:
        path = directory / asset['name']
        if path.is_symlink() or path.stat().st_size != asset['size'] or sha256(path) != asset['sha256']:
            raise ValueError(f'Release file changed: {asset["name"]}')
    if sha256(directory / 'RELEASE_NOTES.md') != manifest['notes_sha256']:
        raise ValueError('Release notes changed after packaging')
    return manifest


def publish(directory, env, api):
    manifest = validate_bundle(directory, env)
    version, commit = manifest['version'], manifest['commit']
    base = f'/repos/{REPOSITORY}'
    require_merged(api, REPOSITORY, commit)
    require_tag(api, version, commit)
    hub_urls = hub_checks(api, manifest['hub_commit'])
    notes = (directory / 'RELEASE_NOTES.md').read_text(encoding='utf-8')
    notes += f'\nPinned Hub checks: [tests]({hub_urls[0]}), [CodeQL]({hub_urls[1]}).\n'
    releases = api.request('GET', base + '/releases?per_page=100')
    matches = [r for r in releases if r['tag_name'] == 'v' + version]
    if len(matches) > 1:
        raise ValueError('Multiple releases exist for this tag')
    if matches:
        release = matches[0]
        if not release['draft']:
            raise ValueError('This release is already published; use a new candidate version')
        if (release['target_commitish'] != commit or release['body'] != notes or not release['prerelease'] or
                release['name'] != f'LBRY SDK NG {version}'):
            raise ValueError('Existing draft belongs to a different release bundle')
    else:
        release = api.request('POST', base + '/releases', {
            'tag_name': 'v' + version, 'target_commitish': commit, 'name': f'LBRY SDK NG {version}',
            'body': notes, 'draft': True, 'prerelease': True, 'make_latest': 'false',
        })
    release_path = base + f'/releases/{release["id"]}'
    expected = {a['name']: a for a in manifest['assets']}
    if any(a['name'] not in expected for a in release['assets']):
        raise ValueError('Existing draft contains unexpected assets')
    for name, asset in expected.items():
        existing = [a for a in release['assets'] if a['name'] == name]
        if existing:
            uploaded = existing[0]
        else:
            uploaded = api.request('POST', release_path + '/assets?name=' + urllib.parse.quote(name),
                                   file=directory / name)
        if (uploaded.get('digest') != 'sha256:' + asset['sha256'] or
                uploaded['size'] != asset['size'] or uploaded['state'] != 'uploaded'):
            raise ValueError(f'Uploaded asset does not match the tested bundle: {name}')
    reviewed = api.request('GET', release_path)
    if (not reviewed['draft'] or not reviewed['prerelease'] or reviewed['body'] != notes or
            reviewed['target_commitish'] != commit or len(reviewed['assets']) != len(expected)):
        raise ValueError('Draft changed during upload')
    if {a['name'] for a in reviewed['assets']} != set(expected):
        raise ValueError('Draft asset list changed during upload')
    for asset in reviewed['assets']:
        local = expected.get(asset['name'])
        if (not local or asset.get('digest') != 'sha256:' + local['sha256'] or
                asset['size'] != local['size'] or asset['state'] != 'uploaded'):
            raise ValueError('Draft assets changed during upload')
    require_tag(api, version, commit)
    published = api.request('PATCH', release_path, {'draft': False, 'prerelease': True, 'make_latest': 'false'})
    if published['draft'] or not published['prerelease']:
        raise ValueError('GitHub did not publish a prerelease')
    return published['html_url']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'publish'))
    parser.add_argument('--artifacts', type=Path, default=Path('artifacts'))
    parser.add_argument('--output', type=Path, default=Path('release'))
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(Path(__file__).resolve().parents[1], args.artifacts, args.output,
                os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'])
    else:
        # Reject local/PR invocations before consulting credentials or making API calls.
        validate_bundle(args.output, os.environ)
        print(publish(args.output, os.environ, GitHub(os.environ['GH_TOKEN'])))


if __name__ == '__main__':
    main()
