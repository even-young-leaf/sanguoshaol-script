"""用本次试跑的真实截图检查免费/付费状态，不操作鼠标。"""
import json
from pathlib import Path
from PIL import Image
import sgs_daily as sgs

ROOT = Path(__file__).resolve().parent
recipes = json.loads((ROOT / "recipes.json").read_text())


def frame(run, stem):
    folder = ROOT / "runs" / run
    data = json.loads((folder / f"{stem}.json").read_text())
    return Image.open(folder / f"{stem}.png").convert("RGB"), data


class NoMouse:
    pixel_scale = (2, 2)

    def hover(self, point):
        pass


class Replay:
    execute = True
    desktop = NoMouse()

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.clicks = []

    def observe(self, label):
        return self.snapshot

    def log(self, *args, **kwargs):
        pass

    def act(self, *args):
        self.clicks.append(args)
        raise AssertionError("已领完/付费状态不应产生点击")


def main():
    if not (ROOT / 'runs' / '20261126-005945-327121' / '001-start.png').exists():
        print('SKIP 本机历史运行截图未包含在仓库中，无法执行截图回放。')
        return
    active, _ = frame("20261126-005945-327121", "001-start")
    done, _ = frame("20261126-005945-327121", "002-after-0")
    sign = recipes["签到"]
    assert sgs.match_template(active, sign["action_template"])
    assert not sgs.match_template(done, sign["action_template"])
    assert sgs.match_template(done, sign["done_template"])
    print("PASS 签到/补签模板互相区分")

    draw, texts = frame("20261126-010810-251200", "001-start")
    draw_recipe = recipes["武将抽取"]
    assert sgs.find_text(texts, draw_recipe["free_guard_labels"],
                         draw_recipe["free_guard_region"], .4)
    assert sgs.has_red_dot(draw, draw_recipe["red_dot_region"], 2)
    print("PASS 免费单抽具有免费文字和对应红点")

    cases = [
        ("签到", "20261126-005945-327121", "002-after-0"),
        ("任务", "20261126-010151-036779", "005-start"),
        ("官阶", "20261126-010324-741456", "002-after-0"),
        ("公会擂鼓", "20261126-010649-706934", "002-free-check"),
        ("武将抽取", "20261126-010810-251200", "002-after-0"),
        ("活动", "20261126-011702-299774", "002-after-0"),
    ]
    for module, run, stem in cases:
        replay = Replay(frame(run, stem))
        sgs.run_module(replay, module)
        assert not replay.clicks
        print(f"PASS {module} 已领完/免费次数用尽后不点击")
    _, texts = frame("20261126-010649-706934", "002-free-check")
    assert sgs.free_count(texts, recipes["公会擂鼓"]["free_counter"]) == 0
    print("PASS 击鼓次数已用完被解析为0")


if __name__ == "__main__":
    main()
