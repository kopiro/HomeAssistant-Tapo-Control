"""Exercise the actual sync/cleanup predicates without HA dependencies."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).parents[1] / 'custom_components/tapo_control'


def evaluate(node, **values):
    return eval(compile(ast.Expression(node), '<predicate>', 'eval'), {}, values)


class RetentionTests(unittest.TestCase):
    def test_both_sync_loops_include_old_clips_when_unlimited(self):
        tree = ast.parse((ROOT / '__init__.py').read_text())
        predicates = [n.test for n in ast.walk(tree) if isinstance(n, ast.If)
                      and 'recording[recordingKey]' in ast.unparse(n.test)
                      and 'mediaSyncTime' in ast.unparse(n.test)]
        self.assertEqual(len(predicates), 2)
        for predicate in predicates:
            values = dict(recording={'clip': {'endTime': 100}}, recordingKey='clip', ts=1000)
            self.assertTrue(evaluate(predicate, mediaSyncTime=False, **values))
            self.assertFalse(evaluate(predicate, mediaSyncTime=60, **values))
            self.assertTrue(evaluate(predicate, mediaSyncTime=1000, **values))

    def test_camera_rotation_cleanup_is_guarded_by_bounded_history(self):
        tree = ast.parse((ROOT / 'utils.py').read_text())
        cleanup = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'mediaCleanup')
        guards = [n for n in cleanup.body if isinstance(n, ast.If)
                  and 'deleteFilesNoLongerPresentInCamera' in ast.unparse(n)]
        self.assertEqual(len(guards), 1)
        calls = [n for n in ast.walk(guards[0]) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'deleteFilesNoLongerPresentInCamera']
        self.assertEqual(len(calls), 2)
        for hours, expected in [('', False), (24, True)]:
            self.assertEqual(evaluate(guards[0].test, entry=SimpleNamespace(data={'media_sync_hours': hours}),
                                      MEDIA_SYNC_HOURS='media_sync_hours'), expected)
