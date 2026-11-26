"""任务、银两宝箱与发财树150元宝预算回归，不操作真实鼠标。"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from sgs_fast import Bot, ROOT, SIZE
from sgs_runs import RunSession
from sgs_tree import TreeSpendLedger


class NoMouse:
    execute = True

    def active_time(self):
        return time.perf_counter()

    def move(self, point):
        pass


class TaskTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Bot(NoMouse(), session=RunSession(Path(self.tmp.name)/'runs'))
        self.b.last = Image.new('RGB', SIZE, (100, 100, 100))
        self.clicks, self.exits = [], []
        self.b.tap = lambda point, action: self.clicks.append((point, action))
        self.b.lobby = lambda: self.exits.append(True)

    def tearDown(self):
        self.b.finish()
        self.tmp.cleanup()

    def test_task_claim_variant_requires_green_background(self):
        b = self.b
        image = Image.open(ROOT/b.spec['task_claim']['file']).convert('RGB')
        ImageDraw.Draw(b.last).rectangle((1180, 520, 1340, 580), fill=(0, 130, 50))
        b.last.paste(image, (1243, 547))
        found = b.claim_buttons((1150, 470, 220, 440))
        self.assertTrue(found)
        ImageDraw.Draw(b.last).rectangle((1180, 520, 1340, 580), fill=(80, 80, 80))
        self.assertEqual(b.claim_buttons((1150, 470, 220, 440)), [])

    def test_silver_progress_and_ocr_separator(self):
        b = self.b
        b.wait = lambda *args: None
        b.text = lambda box: [('3/3', (768, 449)), ('616', (1045, 449)), ('3/9', (1325, 449))]
        b.task_silver_done = lambda point: False
        b.reward_result = lambda *args, **kwargs: True
        b.task_silver()
        self.assertEqual([point for point, _ in self.clicks], [(768, 404), (1045, 404)])

    def test_real_silver_claim_stamp(self):
        files = [ROOT/'calibration_v2/silver-unclaimed.png', ROOT/'calibration_v2/silver-claimed.png']
        if not all(p.exists() for p in files):
            self.skipTest('本机银两实拍截图不在仓库中')
        self.b.last = Image.open(files[0]).convert('RGB')
        self.assertFalse(self.b.task_silver_done((768, 404)))
        self.b.last = Image.open(files[1]).convert('RGB')
        self.assertTrue(self.b.task_silver_done((768, 404)))

    def test_ledger_blocks_repeat_including_pending_request(self):
        ledger = TreeSpendLedger(Path(self.tmp.name)/'tree.json')
        self.assertTrue(ledger.reserve('2026-11-27'))
        self.assertFalse(TreeSpendLedger(ledger.path).reserve('2026-11-27'))
        self.assertTrue(ledger.confirm('2026-11-27'))
        self.assertFalse(ledger.reserve('2026-11-27'))
        self.assertTrue(ledger.reserve('2026-11-28'))

    def paid_page(self):
        b = self.b
        b.wait = b.navigate = lambda *args: None
        b.matches = lambda name, **kwargs: {'tree': [(300,400)], 'tree_entry': [(1370,750)], 'tree_price_150': [(870,765)]}.get(name, [])
        b.text = lambda box: [('150', (880,765))] if box == (780,735,150,60) else []
        b.tree_ledger = TreeSpendLedger(Path(self.tmp.name)/'tree.json')
        b.tree_result = lambda **kwargs: True

    def test_paid_tree_runs_once_and_always_exits(self):
        self.paid_page()
        self.b.tree();self.b.tree()
        paid = [action for _, action in self.clicks if '本日上限150' in action]
        self.assertEqual(len(paid), 1)
        self.assertEqual(len(self.exits), 4)
        self.assertEqual(json.loads(self.b.tree_ledger.path.read_text())['status'], 'confirmed')

    def test_zero_budget_never_pays(self):
        self.paid_page();self.b.tree_budget = 0
        self.b.tree()
        self.assertEqual(len(self.clicks), 1)  # 仅打开更多菜单。
        self.assertFalse(self.b.tree_ledger.path.exists())
        self.assertEqual(len(self.exits), 2)

    def test_tree_loot_is_not_another_paid_click(self):
        b = self.b
        source = Image.open(ROOT/b.spec['tree_drop']['file']).convert('RGB')
        for x, y in [(480,780),(620,780),(760,780),(900,780),(480,850),(620,850),(760,850),(900,850)]:
            b.last.paste(source, (x,y))
        original = b.matches
        state = {'price': True}
        b.matches = lambda name, **kwargs: ([(300,400)] if name == 'tree' else ([(870,765)] if state['price'] else [])) if name in ('tree','tree_price_150') else ([] if name == 'tree_done' else original(name, **kwargs))
        self.assertEqual(b.tree_drops(), [])
        state['price'] = False
        self.assertEqual(len(b.tree_drops()), 8)

    def test_free_branch_does_not_accept_paid_confirmation(self):
        b = self.b
        clock = {'value': 0.}
        b.now = lambda: clock['value']
        b.snap = lambda: clock.update(value=clock['value']+.1)
        b.matches = lambda *args, **kwargs: []
        b.tree_drops = lambda: []
        b.text = lambda box: [('发财树消耗150元宝', (800,500)), ('确认', (900,600)), ('取消', (700,600))]
        self.assertFalse(b.tree_result())
        self.assertEqual(self.clicks[0][0], (700,600))
        self.assertNotIn('确认仅消耗150元宝砍树', [action for _, action in self.clicks])


if __name__ == '__main__':
    unittest.main()
