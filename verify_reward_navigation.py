"""漏领回归：位移后的俸禄红点、无红点的免费行、奖励继续及收费跳过。"""
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from sgs_fast import Bot, ROOT, SIZE, is_continue_caption
from sgs_runs import RunSession


class NoMouse:
    execute = True

    def active_time(self):
        return time.perf_counter()

    def move(self, point):
        pass


class RewardNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bot = Bot(NoMouse(), session=RunSession(self.temp.name))
        self.bot.last = Image.new('RGB', SIZE, (100, 100, 100))
        self.bot.lobby = lambda: None
        self.clicks = []
        self.bot.tap = lambda p, action: self.clicks.append((p, action))

    def tearDown(self):
        self.bot.finish()
        self.temp.cleanup()

    def test_continue_labels_exclude_purchases(self):
        for text in ('点击任意处继续', '点击空白处关闭', '点击任意位置退出', '点击任意地方', '点击屏幕继续'):
            self.assertTrue(is_continue_caption(text), text)
        for text in ('购买', '前往充值', '再抽一次', '点击任意武将查看详情', '兑换奖励', '消耗150元宝砍树'):
            self.assertFalse(is_continue_caption(text), text)

    def test_continue_clicks_recognized_caption_position(self):
        b = self.bot
        b.text = lambda box: [('点击空白处关闭', (830, 940))]
        b.snap = lambda: None
        with patch('sgs_fast.time.sleep'):
            self.assertTrue(b.dismiss_continue())
        self.assertEqual(self.clicks[0][0], (830, 940))

    def test_continue_is_read_only_without_execute(self):
        b = self.bot
        b.d.execute = False
        b.text = lambda box: self.fail('只读模式不应为关闭弹窗读取并操作文字')
        self.assertFalse(b.dismiss_continue())
        self.assertEqual(self.clicks, [])

    def test_rank_dot_follows_detected_label(self):
        b = self.bot
        icon = Image.open(ROOT / b.spec['rank_claim']['file']).convert('RGB')
        b.last.paste(icon, (1120, 365))
        point = b.matches('rank_claim')[0]
        dot = (round(point[0] + 35), round(point[1] - 48))
        ImageDraw.Draw(b.last).ellipse((dot[0]-8, dot[1]-8, dot[0]+8, dot[1]+8), fill='red', outline='white', width=2)
        self.assertFalse(b.dot((1213, 307, 28, 29)))
        b.navigate = lambda *args: None
        b.reward_result = lambda *args, **kwargs: True
        b.simple('官阶')
        self.assertTrue(any(action == '免费每日俸禄' for _, action in self.clicks))

    def test_activity_free_row_does_not_require_old_dot(self):
        b = self.bot
        green = Image.open(ROOT / b.spec['green_claim']['file']).convert('RGB')
        b.last.paste(green, (1245, 460))
        state = {'tab': None}
        b.open_side = lambda *args: None
        b.wait = lambda *args: None
        b.dot = lambda *args: False
        b.tap = lambda point, action: state.update(tab=action.split('：')[-1])
        b.text = lambda box: [('充消返利', (333, 355)), ('活跃福利', (333, 655)), ('限时活动', (333, 774))] if box[0] == 240 else [('免费好礼', (980, 424))]
        b.green_claims = lambda anchor, region, **kwargs: len(b.matches('green_claim', region=region, threshold=.93)) if state['tab'] == '充消返利' else 0
        with patch('sgs_fast.time.sleep'):
            b.simple('活动')
        self.assertTrue(any(r.get('tab') == '充消返利' and r.get('confirmed_rewards') == 1 for r in b.events))

    def test_tree_cost_is_not_a_free_claim(self):
        b = self.bot
        b.wait = b.navigate = lambda *args: None
        b.matches = lambda name, **kwargs: [(1370, 750)] if name == 'tree_entry' else []
        b.text = lambda box: [('150', (880, 765))] if box == (780, 735, 150, 60) else []
        b.tree()
        self.assertEqual(len(self.clicks), 1)  # 只有打开更多菜单，没有点击收费树干。
        self.assertIn('150元宝', b.events[-1]['reason'])


if __name__ == '__main__':
    unittest.main()
