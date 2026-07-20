from pathlib import Path

workflow = Path('.github/workflows/dropfinder-cloud.yml')
text = workflow.read_text(encoding='utf-8')
pins = {
    'actions/checkout@v4': 'actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4.3.1',
    'actions/setup-python@v5': 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0',
    'actions/setup-node@v4': 'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020  # v4.4.0',
    'actions/upload-artifact@v4': 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02  # v4.6.2',
    'actions/download-artifact@v4': 'actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093  # v4.3.0',
}
for old, new in pins.items():
    count = text.count(old)
    if count < 1:
        raise SystemExit(f'missing action ref {old}')
    text = text.replace(old, new)
for mutable in pins:
    if mutable in text:
        raise SystemExit(f'mutable action ref remains: {mutable}')
workflow.write_text(text, encoding='utf-8')

test_path = Path('tests/test_dropfinder_cloud_workflow_permissions.py')
test = test_path.read_text(encoding='utf-8')
anchor = '''    def test_permission_regression_runs_when_it_changes(self) -> None:
        path_entry = '      - "tests/test_dropfinder_cloud_workflow_permissions.py"'
        self.assertEqual(self.text.count(path_entry), 2)
        self.assertIn("tests.test_dropfinder_cloud_workflow_permissions", self.text)
        self.assertIn("tests.test_publication_release", self.text)
'''
addition = anchor + '''
    def test_release_actions_are_immutably_pinned(self) -> None:
        expected = {
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5": 3,
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065": 2,
            "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020": 2,
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02": 2,
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093": 1,
        }
        for action, count in expected.items():
            self.assertEqual(self.text.count(action), count, action)
        for mutable in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v4",
            "actions/upload-artifact@v4",
            "actions/download-artifact@v4",
        ):
            self.assertNotIn(mutable, self.text)
'''
if test.count(anchor) != 1:
    raise SystemExit(f'test anchor count: {test.count(anchor)}')
test_path.write_text(test.replace(anchor, addition, 1), encoding='utf-8')
