from pathlib import Path
import unittest

import yaml


class WorkflowTests(unittest.TestCase):
    def load(self, name):
        # BaseLoader avoids YAML 1.1 interpreting GitHub's `on` as a boolean.
        return yaml.load(Path(f'.github/workflows/{name}.yml').read_text(), Loader=yaml.BaseLoader)

    def test_unprivileged_tests_for_push_and_pull_requests(self):
        workflow = self.load('test')
        self.assertEqual(set(workflow['on']), {'push', 'pull_request'})
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        self.assertNotIn('secrets.', str(workflow))
        self.assertNotIn('write', str(workflow))
        self.assertNotIn('lab_index --publish', str(workflow))

    def test_update_trusted_default_branch_and_serial_full_run(self):
        workflow = self.load('update-index')
        self.assertEqual(set(workflow['on']), {'schedule', 'workflow_dispatch'})
        self.assertEqual(workflow['on']['schedule'], [{'cron': '17 6,18 * * *'}])
        self.assertEqual(workflow['permissions'], {})
        self.assertEqual(workflow['concurrency'], {'group': 'lab-index-update', 'cancel-in-progress': 'false'})
        job = workflow['jobs']['update']
        self.assertIn("github.repository_owner == 'dydojopka'", job['if'])
        self.assertIn("github.ref == format('refs/heads/{0}', github.event.repository.default_branch)", job['if'])
        self.assertEqual(job['permissions'], {'contents': 'write'})
        self.assertEqual(job['timeout-minutes'], '15')
        steps = job['steps']
        self.assertEqual(steps[0]['with']['ref'], '${{ github.sha }}')
        for step in steps[:-1]:
            self.assertNotIn('LABS_READ_TOKEN', str(step))
        self.assertEqual(steps[-1]['env'], {'LABS_READ_TOKEN': '${{ secrets.LABS_READ_TOKEN }}',
                                          'INDEX_WRITE_TOKEN': '${{ github.token }}'})
        self.assertIn('unittest discover', steps[-2]['run'])
        self.assertEqual(steps[-1]['run'], 'python -m lab_index --publish')
        self.assertNotIn('continue-on-error', str(workflow))

    def test_actions_pinned_credentials_not_persisted_python_version_explicit(self):
        for name in ('test', 'update-index'):
            workflow = self.load(name)
            for job in workflow['jobs'].values():
                self.assertEqual(job['runs-on'], 'ubuntu-24.04')
                for step in job['steps']:
                    if 'uses' in step:
                        self.assertRegex(step['uses'], r'^actions/[a-z-]+@[0-9a-f]{40}$')
                    if step.get('uses', '').startswith('actions/checkout@'):
                        self.assertEqual(step['with']['persist-credentials'], 'false')
                    if step.get('uses', '').startswith('actions/setup-python@'):
                        self.assertEqual(step['with']['python-version'], '3.11')
                self.assertNotIn('upload-artifact', str(job))
                self.assertNotIn('cache:', str(job))
