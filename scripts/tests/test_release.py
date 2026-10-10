import copy
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('release', Path(__file__).resolve().parents[1] / 'release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        # enterContext keeps the directory alive until unittest runs the cleanups.
        # pylint: disable-next=consider-using-with
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / 'source'
        self.artifacts = self.root / 'artifacts'
        self.output = self.root / 'release'
        (self.source / 'lbry').mkdir(parents=True)
        (self.source / 'docs/releases').mkdir(parents=True)
        (self.source / 'lbry/__init__.py').write_text('__version__ = "0.114.0rc2"\n')
        (self.source / 'setup.py').write_text(
            "'hub@git+https://github.com/kodxana/lbry-hub-ng.git@" + 'b' * 40 + "'\n")
        (self.source / 'docs/releases/0.114.0rc2.md').write_text('[Install](../../INSTALL.md)\n')
        for name in release.CI_REPORTS:
            path = self.artifacts / name
            path.mkdir(parents=True)
            (path / 'test.log').write_text('Test results\n')
            (path / 'packages.txt').write_text('Dependency inventory\n')
        for platform in ('linux', 'windows', 'macos'):
            path = self.artifacts / ('lbrynet-' + platform)
            path.mkdir()
            (path / ('lbrynet.exe' if platform == 'windows' else 'lbrynet')).write_bytes(platform.encode())
        self.env = {
            'GITHUB_REPOSITORY': release.REPOSITORY, 'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '123',
            'GITHUB_REF': 'refs/tags/v0.114.0rc2', 'GITHUB_EVENT_NAME': 'push',
        }

    def prepare(self):
        release.prepare(self.source, self.artifacts, self.output, release.REPOSITORY, 'a' * 40, '123')

    def test_packages_exact_binaries_logs_and_checksums(self):
        self.prepare()
        manifest = release.validate_bundle(self.output, self.env)
        self.assertEqual(len(manifest['assets']), 6)
        for platform in ('linux', 'windows', 'macos'):
            suffix = '.exe' if platform == 'windows' else ''
            self.assertEqual((self.output / f'lbrynet-0.114.0rc2-{platform}-x86_64{suffix}').read_bytes(),
                             platform.encode())
        with zipfile.ZipFile(self.output / 'validation-0.114.0rc2.zip') as archive:
            self.assertEqual(len(archive.namelist()), len(release.CI_REPORTS) * 2)
        for line in (self.output / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(digest, release.sha256(self.output / name))
        self.assertIn('/blob/' + 'a' * 40 + '/INSTALL.md', (self.output / 'RELEASE_NOTES.md').read_text())

    def test_requires_all_platforms_and_reports(self):
        (self.artifacts / 'ci-windows/packages.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing logs or package inventory'):
            self.prepare()

    def test_rejects_extra_artifacts(self):
        (self.artifacts / 'unrelated-run').mkdir()
        with self.assertRaisesRegex(ValueError, 'from one run'):
            self.prepare()

    def test_rejects_empty_executable(self):
        (self.artifacts / 'lbrynet-linux/lbrynet').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'nonempty linux executable'):
            self.prepare()

    def test_rejects_mutable_hub_dependency(self):
        (self.source / 'setup.py').write_text("'hub@git+https://github.com/kodxana/lbry-hub-ng.git@master'")
        with self.assertRaisesRegex(ValueError, 'full commit SHA'):
            self.prepare()

    def test_publication_context_is_checked_before_network_access(self):
        self.prepare()
        for key, value in (
            ('GITHUB_REPOSITORY', 'lbryio/lbry-sdk'), ('GITHUB_REF', 'refs/heads/master'),
            ('GITHUB_REF', 'refs/tags/v0.114.0rc3'), ('GITHUB_REF', 'refs/tags/v0.114.0'),
            ('GITHUB_SHA', 'c' * 40), ('GITHUB_RUN_ID', '999'), ('GITHUB_EVENT_NAME', 'pull_request'),
        ):
            with self.subTest(key=key, value=value):
                api = Mock()
                with self.assertRaises(ValueError):
                    release.publish(self.output, {**self.env, key: value}, api)
                api.request.assert_not_called()

    def test_rejects_changed_binary_before_network_access(self):
        self.prepare()
        (self.output / 'lbrynet-0.114.0rc2-linux-x86_64').write_bytes(b'corrupt')
        api = Mock()
        with self.assertRaisesRegex(ValueError, 'Release file changed'):
            release.publish(self.output, self.env, api)
        api.request.assert_not_called()

    def test_rejects_changed_notes(self):
        self.prepare()
        (self.output / 'RELEASE_NOTES.md').write_text('different notes')
        with self.assertRaisesRegex(ValueError, 'notes changed'):
            release.validate_bundle(self.output, self.env)

    def test_stable_versions_cannot_be_published(self):
        self.prepare()
        path = self.output / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['version'] = '0.114.0'
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'release-candidate tag'):
            release.validate_bundle(self.output, {**self.env, 'GITHUB_REF': 'refs/tags/v0.114.0'})

    def api(self, *, already_published=False, bad_digest=False, failed_hub=False, unmerged=False,
            tag_moved=False, existing_draft=False):
        state = {'assets': [], 'id': 42, 'tag_name': 'v0.114.0rc2', 'draft': not already_published}
        if existing_draft:
            notes = (self.output / 'RELEASE_NOTES.md').read_text()
            notes += '\nPinned Hub checks: [tests](https://example.test/ci), [CodeQL](https://example.test/ci).\n'
            state.update(body=notes, target_commitish='a' * 40, prerelease=True, name='LBRY SDK NG 0.114.0rc2')
            manifest = json.loads((self.output / 'manifest.json').read_text())
            for asset in manifest['assets'][:2]:
                state['assets'].append(dict(name=asset['name'], size=asset['size'], state='uploaded',
                                            digest='sha256:' + asset['sha256']))

        def request(method, path, body=None, file=None):
            if '/compare/' in path:
                commit = 'b' * 40 if release.HUB_REPOSITORY in path else 'a' * 40
                return {'merge_base_commit': {'sha': 'c' * 40 if unmerged else commit}}
            if '/git/ref/tags/' in path:
                return {'object': {'type': 'commit', 'sha': 'c' * 40 if tag_moved else 'a' * 40}}
            if '/actions/workflows/' in path:
                return {'workflow_runs': [{'id': 321, 'head_sha': 'b' * 40, 'html_url': 'https://example.test/ci'}]}
            if '/jobs?' in path:
                return {'total_count': 1, 'jobs': [{'conclusion': 'failure' if failed_hub else 'success'}]}
            if method == 'GET' and '/releases?' in path:
                return [state] if already_published or existing_draft else []
            if method == 'POST' and path.endswith('/releases'):
                self.assertTrue(body['draft'])
                self.assertTrue(body['prerelease'])
                self.assertEqual(body['make_latest'], 'false')
                state.update(body)
                return copy.deepcopy(state)
            if method == 'POST' and '/assets?' in path:
                asset = {'name': file.name, 'size': file.stat().st_size, 'state': 'uploaded',
                         'digest': 'sha256:' + ('0' * 64 if bad_digest else release.sha256(file))}
                state['assets'].append(asset)
                return asset
            if method == 'GET' and path.endswith('/releases/42'):
                return copy.deepcopy(state)
            if method == 'PATCH':
                self.assertEqual(len(state['assets']), 6)
                self.assertEqual(body, {'draft': False, 'prerelease': True, 'make_latest': 'false'})
                state.update(body, html_url='https://example.test/release')
                return state
            self.fail((method, path))

        api = Mock()
        api.request.side_effect = request
        return api

    def test_publishes_only_after_verifying_every_uploaded_asset(self):
        self.prepare()
        api = self.api()
        self.assertEqual(release.publish(self.output, self.env, api), 'https://example.test/release')
        self.assertEqual(api.request.call_args.args[0], 'PATCH')

    def test_never_publishes_failed_checks_unmerged_commits_or_bad_uploads(self):
        self.prepare()
        for condition in ('failed_hub', 'bad_digest', 'unmerged', 'tag_moved', 'already_published'):
            with self.subTest(condition=condition):
                api = self.api(**{condition: True})
                with self.assertRaises(ValueError):
                    release.publish(self.output, self.env, api)
                self.assertFalse(any(call.args[0] == 'PATCH' for call in api.request.call_args_list))
        api = self.api(already_published=True)
        with self.assertRaises(ValueError):
            release.publish(self.output, self.env, api)
        self.assertTrue(all(call.args[0] == 'GET' for call in api.request.call_args_list))

    def test_resumes_matching_draft_without_reuploading_existing_assets(self):
        self.prepare()
        api = self.api(existing_draft=True)
        release.publish(self.output, self.env, api)
        posts = [call for call in api.request.call_args_list if call.args[0] == 'POST']
        self.assertEqual(len(posts), 4)
        self.assertTrue(all('/assets?' in call.args[1] for call in posts))


if __name__ == '__main__':
    unittest.main()
