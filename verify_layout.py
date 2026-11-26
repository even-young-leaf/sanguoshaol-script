"""用已公开的局部模板合成画面，验证小幅缩放与入口位置变化。"""
import time
from PIL import Image, ImageEnhance
from sgs_fast import Bot, ROOT, SIZE


class NoInput:
    def active_time(self):
        return time.perf_counter()


b = Bot(NoInput())
canvas = Image.new('RGB', SIZE, (100, 100, 100))
source = Image.open(ROOT / b.spec['lobby']['file']).convert('RGB')
small = source.resize((round(source.width * .97), round(source.height * .97)), Image.Resampling.BILINEAR)
canvas.paste(small, (433, 485))
points = b.matches('lobby', image=canvas)
assert points and abs(points[0][0] - (433 + small.width / 2)) < 2
assert not b.matches('lobby', image=ImageEnhance.Brightness(canvas).enhance(.2))
print('PASS 缩小约 3% 且偏移的大厅标记可定位，遮罩下的暗背景不算前景页')

close_canvas = Image.new('RGB', SIZE, (100, 100, 100))
cross = Image.open(ROOT / b.spec['startup_close']['file']).convert('RGB')
close_canvas.paste(cross, (1375, 273))
found = b.scaled_matches('startup_close', close_canvas, (1384, 247, 50, 50), .85, False)
assert found and abs(found[0][0] - (1375 + cross.width / 2)) < 2
print('PASS 已知页面的关闭叉号按实际位置定位')

b.lobby = lambda: None
b.snap = lambda: None
b.text = lambda box: [('任务', (62, 779))]
actions = []
b.navigate = lambda point, anchor, action: actions.append((point, anchor))
b.tasks_open()
assert actions == [((62, 779), 'task')]
print('PASS 任务入口移到侧栏下方后，使用文字坐标而非旧固定坐标')

from unittest.mock import patch
rows = iter([[('收起.', (62, 850))], [('活动', (62, 276))]])
b.text = lambda box: next(rows)
b.tap = lambda point, action: actions.append((point, 'toggle'))
b.d.move = lambda point: None
with patch('sgs_fast.time.sleep'):
    b.open_side('活动', 'event', '打开活动')
assert actions[-2:] == [((62, 850), 'toggle'), ((62, 276), 'event')]
print('PASS 收起文字含 OCR 尾部句点时仍能切换入口')
