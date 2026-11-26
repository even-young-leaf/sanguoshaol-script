"""用实拍画面检查延迟宣传页处理和非宣传页误判。"""
import time
from pathlib import Path
from PIL import Image
from sgs_fast import Bot, ROOT, SIZE


def shot(name):
    return Image.open(ROOT / 'calibration_v2' / name).convert('RGB').resize(SIZE)


class Replay:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.clicks = []

    def active_time(self):
        return time.perf_counter()

    def capture(self):
        return next(self.frames)

    def tap(self, point):
        self.clicks.append(point)


if not (ROOT / 'calibration_v2' / 'startup-current.png').exists():
    print('SKIP 本机完整校准截图未包含在仓库中，无法执行宣传页回放。')
    raise SystemExit(0)

ad = shot('startup-current.png')
lobby = shot('lobby-clean.png')
d = Replay([ad, lobby, lobby])
b = Bot(d)
b.lobby()
assert len(d.clicks) == 1
assert b.matches('lobby')
assert any(r['event'] == '宣传弹窗关闭已确认' for r in b.events)
b.finish()
print('PASS 领取阶段返回大厅时发现宣传页，关闭并确认后继续')

positives = {'startup-ad.png', 'startup-current.png', 'startup-reported.png'}
checked = 0
for path in (ROOT / 'calibration_v2').glob('*.png'):
    if path.name.endswith('-preview.png'):
        continue
    found = bool(b.matches('startup_close', image=shot(path.name)))
    assert found == (path.name in positives), path.name
    checked += 1
print(f'PASS {checked} 张实拍画面，宣传页叉号与任务、奖励等其他画面区分正确')
