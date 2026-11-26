"""P0/P1 回归：只读、窗口竞态、缩放缓存、日志归并与保留策略。"""
import fcntl
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch

from PIL import Image
from sgs_fast import Bot, FastDesktop, ROOT, SIZE
from sgs_runs import RunSession, prune_runs
from sgs_zoom import ZoomGuard


class ReadOnly:
    execute = False

    def active_time(self):
        return time.perf_counter()

    def capture(self):
        return Image.new('RGB', SIZE)

    def tap(self, point):
        raise AssertionError('只读模式不得点击')


class MaintenanceTests(unittest.TestCase):
    def test_scan_does_not_close_ad(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Bot(ReadOnly(), session=RunSession(tmp))
            b.matches = lambda name, **kwargs: [(1400, 260)] if name == 'startup_close' else []
            b.snap()
            self.assertFalse(b.dismiss_startup())
            self.assertEqual(b.frames, 1)
            b.finish()
            self.assertFalse(any(r['event'] == '点击' for r in b.events))

    def test_window_race_does_not_recurse(self):
        game = dict(kCGWindowOwnerName='Google Chrome', kCGWindowOwnerPID=7,
                    kCGWindowLayer=0, kCGWindowName='4399三国杀 三国杀OL', kCGWindowNumber=1,
                    kCGWindowBounds=dict(X=0, Y=0, Width=1657, Height=1079))
        other = dict(game, kCGWindowName='New Tab', kCGWindowNumber=2)
        calls = 0

        def windows(*args):
            nonlocal calls
            calls += 1
            return [other, game] if calls <= 1500 else [game]

        d = FastDesktop.__new__(FastDesktop)
        d.require_front, d.execute = True, False
        d.wait_foreground = lambda: None
        d.front_application = lambda: S(processIdentifier=lambda: 7)
        d.q = S(CGWindowListCopyWindowInfo=windows, kCGWindowListOptionOnScreenOnly=1,
                CGDisplayBounds=lambda _: S(size=S(width=2000, height=1200)), CGMainDisplayID=lambda: 0)
        self.assertEqual(d.validate_window()['kCGWindowNumber'], 1)
        self.assertEqual(calls, 1501)

    def test_zoom_cache_expires_and_invalidates_on_switch(self):
        guard = ZoomGuard.__new__(ZoomGuard)
        guard.desktop = S(owner_pid=7, window_id=1, bounds=(0, 0, 1657, 1079),
                          window_title='game', focus_epoch=0)
        guard.checked_at, guard.checked_context, guard.cache_seconds = float('-inf'), None, .25
        with patch.object(guard, 'level', return_value=100) as level, patch('sgs_zoom.time.monotonic') as clock:
            clock.return_value = 0
            guard.ensure(); guard.ensure()
            self.assertEqual(level.call_count, 1)
            clock.return_value = .26
            guard.ensure()
            self.assertEqual(level.call_count, 2)
            guard.desktop.focus_epoch += 1
            guard.ensure()
            self.assertEqual(level.call_count, 3)
            guard.ensure(force=True)
            self.assertEqual(level.call_count, 4)

    def test_login_and_claim_share_one_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = RunSession(tmp)
            login = Bot(ReadOnly(), session=session, phase='登录')
            login.log('登录就绪'); login.snap(); login.flush()
            claims = Bot(ReadOnly(), session=session, phase='巡检')
            claims.log('巡检完成'); claims.snap(); claims.finish(); login.finish()
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)
            rows = json.loads((session.folder / 'log.json').read_text())
            self.assertEqual([r['event'] for r in rows], ['登录就绪', '巡检完成', '结束'])
            self.assertEqual(rows[-1]['frames'], 2)
            self.assertEqual([r['elapsed_s'] for r in rows], sorted(r['elapsed_s'] for r in rows))

    def test_retention_preserves_running_and_unrelated_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dirs = []
            for i in range(4):
                p = root / f'20260101-00000{i}-000001';p.mkdir();dirs.append(p)
            notes = root / 'notes';notes.mkdir()
            with (dirs[0] / '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                prune_runs(root, 2)
                self.assertTrue(dirs[0].exists())
                self.assertFalse(dirs[1].exists())
                self.assertTrue(dirs[2].exists() and dirs[3].exists() and notes.exists())

    def test_coarse_search_and_resized_template_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Bot(ReadOnly(), session=RunSession(tmp))
            source = Image.open(ROOT / b.spec['lobby']['file']).convert('RGB')
            small = source.resize((round(source.width * .96), round(source.height * .96)), Image.Resampling.BILINEAR)
            canvas = Image.new('RGB', SIZE, (100, 100, 100));canvas.paste(small, (433, 485))
            self.assertTrue(b.scaled_matches('lobby', canvas, None, .94, False))
            self.assertEqual(set(b.scaled_templates), {('lobby', 1.), ('lobby', .96), ('lobby', 1.04)})
            b.finish()

    def test_latest_completion_frames(self):
        cases = [('sign_done', 'done-sign-current.png'), ('experience_done', 'done-experience-current.png'),
                 ('tree_done', 'done-tree-clear.png')]
        if not all((ROOT / 'calibration_v2' / fn).exists() for _, fn in cases):
            self.skipTest('本机校准截图不在仓库中')
        with tempfile.TemporaryDirectory() as tmp:
            b = Bot(ReadOnly(), session=RunSession(tmp))
            for key, fn in cases:
                with self.subTest(key=key):
                    image = Image.open(ROOT / 'calibration_v2' / fn).convert('RGB')
                    self.assertTrue(b.matches(key, image=image))
            sign = Image.open(ROOT / 'calibration_v2' / cases[0][1]).convert('RGB')
            self.assertFalse(b.matches('sign_free', image=sign))
            tree = Image.open(ROOT / 'calibration_v2' / 'done-tree-current.png').convert('RGB')
            self.assertFalse(b.matches('tree_done', image=tree), '体验卡提示遮挡时不能误报砍树完成')
            b.finish()

    def test_blessing_animation_requires_reward_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Bot(ReadOnly(), session=RunSession(tmp))
            state = {'time': 0., 'reward': False}
            b.now = lambda: state['time']
            b.snap = lambda: state.update(time=state['time'] + .05)
            b.matches = lambda name: name == 'blessing' or (name == 'reward' and state['reward'])
            with patch('sgs_fast.time.sleep'):
                self.assertFalse(b.reward_result('blessing', timeout=.12))
                state['reward'] = True
                b.dismiss = lambda: state.update(reward=False)
                self.assertTrue(b.reward_result('blessing', timeout=.2))
            b.finish()


if __name__ == '__main__':
    unittest.main()
