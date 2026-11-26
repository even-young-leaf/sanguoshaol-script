#!/usr/bin/env python3
"""三国杀 OL 快速巡检：缓存模板、局部 OCR、自动切页与关闭奖励。"""
from __future__ import annotations
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from sgs_daily import Desktop, normalize, red_dots

ROOT = Path(__file__).resolve().parent
SIZE = (1657, 1079)


class FastDesktop(Desktop):
    window_title = '4399三国杀 三国杀OL'
    def __init__(self, execute):
        super().__init__(require_front=execute)
        self.execute = execute
        self.pg.PAUSE = .01
        self.paused_seconds = 0.0
        self.zoom_guard = None

    def active_time(self):
        return time.perf_counter() - self.paused_seconds

    def front_application(self):
        # 让 AppKit 接收应用切换通知；纯 sleep 轮询可能一直读到旧的前台应用。
        from Foundation import NSRunLoop, NSDate
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.001))
        return self.workspace.frontmostApplication()

    def wait_foreground(self, extra_titles=()):
        if not self.require_front:
            return
        started = None
        try:
            while True:
                front = self.front_application()
                windows = self.q.CGWindowListCopyWindowInfo(self.q.kCGWindowListOptionOnScreenOnly, 0)
                top = next((w for w in windows if front
                            and w.get('kCGWindowOwnerPID') == front.processIdentifier()
                            and w.get('kCGWindowLayer') == 0
                            and w.get('kCGWindowBounds', {}).get('Width', 0) >= 300
                            and w.get('kCGWindowBounds', {}).get('Height', 0) >= 200), None)
                ready = (front and front.bundleIdentifier() == 'com.google.Chrome' and top
                         and any(title in top.get('kCGWindowName', '')
                                 for title in (self.window_title, *extra_titles)))
                if ready:
                    return
                if started is None:
                    started = time.perf_counter()
                    print('已暂停：切回 Chrome 的游戏页面后自动继续；Ctrl+C 可结束。', flush=True)
                time.sleep(.15)
        finally:
            if started is not None:
                duration = time.perf_counter() - started
                self.paused_seconds += duration
                print(f'已等待 {duration:.1f} 秒。', flush=True)

    def validate_window(self):
        self.wait_foreground()
        q = self.q
        front = self.front_application()
        windows = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly, 0)
        win = next((w for w in windows if w.get('kCGWindowLayer') == 0
                    and w.get('kCGWindowOwnerName') == 'Google Chrome'
                    and self.window_title in w.get('kCGWindowName', '')), None)
        if not win:
            raise RuntimeError('未找到已登录的三国杀 OL 游戏窗口。')
        bounds = tuple(round(win['kCGWindowBounds'][k]) for k in ('X', 'Y', 'Width', 'Height'))
        if self.require_front:
            top = next((w for w in windows if w.get('kCGWindowOwnerPID') == front.processIdentifier()
                        and w.get('kCGWindowLayer') == 0
                        and w.get('kCGWindowBounds', {}).get('Width', 0) >= 300
                        and w.get('kCGWindowBounds', {}).get('Height', 0) >= 200), None)
            if not top or top['kCGWindowNumber'] != win['kCGWindowNumber']:
                return self.validate_window()
        x, y, w, h = bounds
        screen = q.CGDisplayBounds(q.CGMainDisplayID()).size
        if min(x, y) < 0 or x + w > screen.width or y + h > screen.height:
            raise RuntimeError('请把游戏窗口完整放到主显示器。')
        if hasattr(self, 'initial_bounds') and self.execute and bounds != self.initial_bounds:
            raise RuntimeError('运行期间窗口移动或缩放，停止。')
        self.bounds = bounds
        self.initial_bounds = bounds
        self.window_id = win['kCGWindowNumber']
        self.owner_pid = win['kCGWindowOwnerPID']
        if self.execute:
            if getattr(self, 'zoom_guard', None) is None:
                from sgs_zoom import ZoomGuard
                self.zoom_guard = ZoomGuard(self)
            if self.zoom_guard.ensure():
                # 重排等待期间用户可能切换应用，重新核对后才允许鼠标动作。
                return self.validate_window()
        return win

    def capture(self):
        q = self.q
        win = self.validate_window()
        native = q.CGWindowListCreateImage(q.CGRectNull, q.kCGWindowListOptionIncludingWindow,
                                         win['kCGWindowNumber'], q.kCGWindowImageBoundsIgnoreFraming
                                         | q.kCGWindowImageNominalResolution)
        if native is None:
            raise RuntimeError('窗口截图失败，请检查屏幕录制权限。')
        width, height = q.CGImageGetWidth(native), q.CGImageGetHeight(native)
        raw = q.CGDataProviderCopyData(q.CGImageGetDataProvider(native))
        image = Image.frombytes('RGBA', (width, height), bytes(raw), 'raw', 'BGRA',
                                q.CGImageGetBytesPerRow(native), 1).convert('RGB')
        return image if image.size == SIZE else image.resize(SIZE, Image.Resampling.BILINEAR)

    def tap(self, point):
        if not self.execute:
            raise RuntimeError('观察模式不会点击。')
        self.validate_window()  # 点击前只查窗口元数据，避免重复截图
        q = self.q
        current = q.CGEventGetLocation(q.CGEventCreate(None))
        if current.x <= 2 and current.y <= 2:
            raise RuntimeError('鼠标位于左上角，已中止。')
        x, y, w, h = self.bounds
        pos = (x + point[0] * w / SIZE[0], y + point[1] * h / SIZE[1])
        for kind in (q.kCGEventMouseMoved, q.kCGEventLeftMouseDown):
            q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateMouseEvent(None, kind, pos, q.kCGMouseButtonLeft))
        time.sleep(.06)
        q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateMouseEvent(
            None, q.kCGEventLeftMouseUp, pos, q.kCGMouseButtonLeft))

    def move(self, point):
        self.validate_window()
        x, y, w, h = self.bounds
        pos = (x + point[0] * w / SIZE[0], y + point[1] * h / SIZE[1])
        q = self.q
        q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateMouseEvent(
            None, q.kCGEventMouseMoved, pos, q.kCGMouseButtonLeft))

    def scroll(self, point, amount):
        self.move(point)
        self.validate_window()
        self.pg.scroll(amount)


class Bot:
    def now(self):
        return self.d.active_time()

    def __init__(self, desktop, debug=False, deadline=90):
        self.d = desktop
        self.debug = debug
        self.started = self.now()
        self.deadline = self.started + deadline
        self.events = []
        self.frames = 0
        self.ocr_calls = 0
        self.spec = json.loads((ROOT / 'templates_v2.json').read_text())
        self.templates = {}
        for key, spec in self.spec.items():
            self.templates[key] = cv2.cvtColor(np.array(Image.open(ROOT / spec['file']).convert('RGB')),
                                                cv2.COLOR_RGB2GRAY)
        self.folder = ROOT / 'fast_runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.last = None

    def log(self, event, **values):
        row = {'elapsed_s': round(self.now() - self.started, 3), 'event': event, **values}
        self.events.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def snap(self):
        if self.now() >= self.deadline:
            raise RuntimeError('超过本次运行时间上限，停止。')
        self.last = self.d.capture()
        self.frames += 1
        if self.debug:
            self.last.save(self.folder / f'{self.frames:04d}.jpg', quality=80)
        return self.last

    def matches(self, name, image=None, region=None, threshold=.94, multiple=False):
        image = image if image is not None else self.last
        target = self.templates[name]
        x, y, w, h = region or self.spec[name]['region']
        crop = np.array(image.crop((x, y, x + w, y + h)).convert('RGB'))
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        th, tw = target.shape
        if h < th or w < tw:
            return []
        scores = cv2.matchTemplate(gray, target, cv2.TM_CCOEFF_NORMED)
        points = []
        for _ in range(24 if multiple else 1):
            _, score, _, loc = cv2.minMaxLoc(scores)
            if score < threshold:
                break
            lx, ly = loc
            # 图形形状和亮度共同检查，暗下来的弹窗背景不能当成前景页。
            sample = gray[ly:ly + th, lx:lx + tw]
            if abs(float(sample.mean()) - float(target.mean())) > 24:
                break
            points.append((x + lx + tw / 2, y + ly + th / 2))
            scores[max(0, ly - th // 2):ly + th, max(0, lx - tw // 2):lx + tw] = -1
        return sorted(points, key=lambda p: (p[1], p[0]))

    def dot(self, box):
        x, y, w, h = box
        im = self.last.crop((x, y, x + w, y + h))
        return bool(red_dots(im, 1))

    def text(self, box):
        self.ocr_calls += 1
        x, y, w, h = box
        crop = self.last.crop((x, y, x + w, y + h))
        # 局部 OCR 不缩小汉字；识别坐标映射回窗口。
        rows = self.d.read(crop.resize((w * 2, h * 2), Image.Resampling.BILINEAR))
        return [(r['text'], (x + (r['box'][0] + r['box'][2] / 2) * w,
                            y + (r['box'][1] + r['box'][3] / 2) * h)) for r in rows]

    def tap(self, point, action):
        self.log('点击', action=action)
        self.d.tap(point)

    def dismiss(self):
        # 宣传页可能在登录后延迟出现，所有页面等待都需要处理。
        close = self.matches('startup_close')
        if close:
            self.startup_close_attempts = getattr(self, 'startup_close_attempts', 0) + 1
            if self.startup_close_attempts > 5:
                raise RuntimeError('活动宣传页连续五次未能关闭，已停止并保存截图。')
            self.tap(close[0], '关闭活动宣传弹窗')
            time.sleep(.2)
            self.snap()
            if not self.matches('startup_close'):
                self.log('宣传弹窗关闭已确认')
                self.startup_close_attempts = 0
            return True
        self.startup_close_attempts = 0
        # 奖励标题模板已知时，仅在前景标题出现后点击预先核对过的空白区域。
        if 'reward' in self.templates and self.matches('reward'):
            self.tap((1320, 790), '关闭奖励弹窗')
            return True
        if self.matches('experience_done'):
            return False  # 提示条不阻挡页面
        return False

    def wait(self, anchor, timeout=3):
        end = self.now() + timeout
        while self.now() < end:
            self.snap()
            if self.dismiss():
                continue
            if self.matches(anchor):
                return self.last
            time.sleep(.035)
        raise RuntimeError(f'页面未就绪：{anchor}。已保存最后画面，未继续盲点。')

    def navigate(self, point, anchor, name):
        self.tap(point, name)
        return self.wait(anchor)

    def lobby(self):
        for _ in range(7):
            self.snap()
            if self.dismiss():
                continue
            if self.matches('lobby'):
                return
            known = [('task', (1411, 262)), ('welfare', (1409, 272)),
                     ('event', (1409, 272)), ('rank', (1411, 262)),
                     ('tree', (1510, 265)), ('draw', (1517, 214)),
                     ('guild_drums', (1258, 279)), ('guild_home', (1258, 255)),
                     ('blessing', (1632, 133))]
            match = next(((name, point) for name, point in known if self.matches(name)), None)
            if match:
                self.tap(match[1], '返回大厅：' + match[0])
                time.sleep(.08)
            else:
                raise RuntimeError('当前有未适配的页面或弹窗；请返回大厅后重试。')
        raise RuntimeError('未能返回大厅。')

    def tasks_open(self):
        self.side('task')
        self.navigate((64, 430), 'task', '打开任务')

    def side(self, group):
        self.lobby()
        if not self.matches('side_' + group):
            other = 'side_activity' if group == 'task' else 'side_task'
            if not self.matches(other):
                raise RuntimeError('左侧菜单不是已校准的布局。')
            self.tap((64, 765), '切换左侧入口组')
            self.wait('side_' + group)

    def reward_result(self, anchor, watch_box, before, timeout=2, verify=None):
        end = self.now() + timeout
        overlay = False
        while self.now() < end:
            self.snap()
            if 'reward' in self.templates and self.matches('reward'):
                self.log('奖励弹窗已确认')
                self.dismiss()
                overlay = True
                continue
            if self.matches(anchor):
                x, y, w, h = watch_box
                after = np.array(self.last.crop((x, y, x + w, y + h)).convert('RGB'))
                if overlay or (verify is not None and verify()):
                    return True
            time.sleep(.04)
        self.log('未验证', reason='尚未观察到明确的奖励弹窗或领取状态变化')
        return False

    def passes(self, module):
        anchor, point, button = {
            '军典': ('military', (318, 514), 'military_claim'),
            '节钺令': ('scepter', (318, 575), 'scepter_claim'),
        }[module]
        self.wait('task')
        self.navigate(point, anchor, '切换' + module)
        dot_box = (514, 288, 28, 35) if module == '军典' else (531, 291, 26, 32)
        if not self.dot(dot_box):
            self.log('跳过', module=module, reason='当前页没有待领取红点')
            return
        found = self.matches(button)
        if not found:
            self.log('跳过', module=module, reason='没有匹配到一键领取按钮')
            return
        box = (740, 440, 380, 405)
        before = np.array(self.last.crop((box[0], box[1], box[0] + box[2], box[1] + box[3])))
        self.tap(found[0], module + '一键领取（不购买通行证）')
        verified = self.reward_result(anchor, box, before, verify=lambda: not self.dot(dot_box))
        self.log('模块完成', module=module, verified=verified)

    def green_claims(self, anchor, region, pages=1):
        for page in range(pages):
            self.wait(anchor)
            for _ in range(16):
                buttons = self.matches('green_claim', region=region, threshold=.93, multiple=True)
                if not buttons:
                    break
                point = buttons[0]
                sample = np.array(self.last.crop((point[0] - 45, point[1] - 14,
                                                  point[0] + 45, point[1] + 14)))
                hsv = cv2.cvtColor(sample, cv2.COLOR_RGB2HSV)
                green = cv2.inRange(hsv, (35, 70, 40), (95, 255, 255))
                if np.mean(green > 0) < .20:
                    break
                box = (int(point[0] - 60), int(point[1] - 24), 120, 48)
                before = np.array(self.last.crop((box[0], box[1], box[0] + 120, box[1] + 48)))
                self.tap(point, '领取当前已完成的免费任务奖励')
                if not self.reward_result(anchor, box, before,
                                          verify=lambda: not self.matches('green_claim', region=box, threshold=.93)):
                    break
                self.wait(anchor)
            if page + 1 < pages:
                self.d.scroll((1250, 760), -12)
                time.sleep(.06)

    def task_bundle(self):
        self.tasks_open()
        self.navigate((318, 390), 'experience', '打开我要强将')
        self.tap((1326, 414), '领取每日体验卡')
        end = self.now() + .5
        while self.now() < end:
            self.snap()
            if self.matches('experience_done') or self.matches('reward'):
                break
            time.sleep(.02)
        if self.matches('experience_done'):
            self.log('已完成', module='每日体验卡', reason='今日已获得过体验卡')
        elif self.dismiss():
            self.log('奖励已确认', module='每日体验卡')
        else:
            self.log('已提交', module='每日体验卡', verified=False)
        self.navigate((622, 315), 'ascension', '切换羽化飞升')
        self.green_claims('ascension', (1185, 340, 162, 530), pages=6)
        self.log('模块完成', module='羽化飞升', note='只查领取按钮，跳过兑换、前往及未完成项')
        self.navigate((318, 452), 'task', '切换日常任务')
        self.green_claims('task', (1195, 460, 165, 440), pages=6)
        for module in ('军典', '节钺令'):
            self.passes(module)
        self.lobby()

    def simple(self, module):
        if module == '签到':
            self.side('task')
            self.navigate((64, 514), 'welfare', '打开福利签到')
            self.tap((319, 469), '选择每日签到标签')
            end = self.now() + 1.5
            while self.now() < end:
                self.snap()
                if self.matches('sign_done') or self.matches('sign_free'):
                    break
                time.sleep(.04)
            if self.matches('sign_done'):
                self.log('已完成', module=module)
            else:
                points = self.matches('sign_free')
                if points:
                    box = (1230, 835, 140, 80)
                    before = np.array(self.last.crop((1230, 835, 1370, 915)))
                    self.tap(points[0], '今日免费签到')
                    ok = self.reward_result('welfare', box, before,
                                             verify=lambda: bool(self.matches('sign_done')))
                    self.log('模块完成', module=module, verified=ok)
                else:
                    self.log('跳过', module=module, reason='没有今日免费签到按钮')
        elif module == '官阶':
            self.lobby()
            self.navigate((1426, 1048), 'rank', '打开官阶')
            box = (1213, 307, 28, 29)
            if self.dot(box) and self.matches('rank_claim'):
                before = np.array(self.last.crop((1130, 305, 1245, 400)))
                self.tap(self.matches('rank_claim')[0], '免费每日俸禄')
                ok = self.reward_result('rank', (1130, 305, 115, 95), before,
                                         verify=lambda: not self.dot(box))
                self.log('模块完成', module=module, verified=ok)
            else:
                self.log('跳过', module=module, reason='没有待领取俸禄红点')
        elif module == '活动':
            self.side('activity')
            self.navigate((64, 260), 'event', '打开活动')
            if self.dot((1333, 430, 27, 32)):
                rows = self.text((925, 395, 125, 38))
                if not any('免费好礼' in t for t, _ in rows):
                    raise RuntimeError('当前活动不是已校准的免费好礼页。')
                points = self.matches('green_claim', region=(1210, 438, 153, 60), threshold=.93)
                if points:
                    before = np.array(self.last.crop((1210, 438, 1363, 498)))
                    self.tap(points[0], '活动免费好礼')
                    ok = self.reward_result('event', (1210, 438, 153, 60), before,
                                             verify=lambda: not self.dot((1333, 430, 27, 32)))
                    self.log('模块完成', module=module, verified=ok)
            else:
                self.log('跳过', module=module, reason='免费好礼没有红点')
        elif module == '武将抽取':
            self.lobby()
            self.navigate((1528, 1048), 'draw', '打开招募')
            box = (768, 781, 27, 32)
            if self.dot(box):
                if not any(normalize(t) == '免费开启' for t, _ in self.text((695, 925, 105, 35))):
                    raise RuntimeError('免费单抽文字未确认，不使用招募令。')
                self.tap((731, 820), '免费单次抽将')
                end = self.now() + 8
                while self.now() < end:
                    self.snap()
                    # 抽将弹窗以“点击空白处关闭”确认；不点再次抽取。
                    labels = self.text((730, 740, 230, 100))
                    caption = next((p for t, p in labels if '空白' in t and '关闭' in t), None)
                    if caption:
                        self.tap(caption, '关闭抽将结果')
                        self.log('奖励已确认', module=module)
                        self.wait('draw')
                        break
                    time.sleep(.08)
                else:
                    raise RuntimeError('抽将结果弹窗未确认，停止且不会再次抽取。')
            else:
                self.log('跳过', module=module, reason='没有免费单抽红点')
        elif module == '祈福':
            self.side('activity')
            self.navigate((64, 512), 'blessing', '打开祈福')
            free = self.matches('blessing_free')
            if free and self.dot((749, 918, 29, 29)):
                before = np.array(self.last.crop((630, 935, 770, 985)))
                self.tap(free[0], '免费祈福')
                ok = self.reward_result('blessing', (630, 935, 140, 50), before, timeout=12,
                                         verify=lambda: not self.matches('blessing_free'))
                self.log('模块完成', module=module, verified=ok)
            else:
                self.log('跳过', module=module, reason='没有明确免费祈福按钮和对应红点')
        self.lobby()

    def guild(self):
        self.lobby()
        self.navigate((1209, 1048), 'guild_home', '打开公会')
        self.navigate((731, 894), 'guild_drums', '打开公会擂鼓')
        previous = None
        for _ in range(4):
            self.d.move((400, 175))
            self.d.move((552, 875))
            time.sleep(.6)
            self.snap()
            if self.matches('guild_done'):
                self.log('已完成', module='公会擂鼓', reason='今日次数已用完')
                break
            words = ''.join(normalize(t) for t, _ in self.text((380, 780, 330, 45)))
            if '击鼓次数已用完' in words:
                self.log('已完成', module='公会擂鼓', reason='今日次数已用完')
                break
            match = re.search(r'不消耗道具.*还可以击鼓([1-3])次', words)
            if not match:
                self.log('跳过', module='公会擂鼓', reason='未确认不消耗道具和免费次数', tooltip=words)
                break
            count = int(match.group(1))
            if previous is not None and count >= previous:
                self.log('停止当前模块', module='公会擂鼓', reason='未观察到免费次数减少')
                break
            self.tap((552, 875), '常山战鼓免费次数')
            previous = count
        self.lobby()

    def all(self):
        self.simple('签到')
        self.task_bundle()
        for module in ('官阶', '武将抽取'):
            self.simple(module)
        self.guild()
        self.simple('活动')
        self.simple('祈福')
        self.tree()

    def tree(self):
        self.lobby()
        self.tap((1628, 1048), '打开更多菜单')
        self.wait('tree_entry')
        self.navigate(self.matches('tree_entry')[0], 'tree', '进入发财树')
        if self.matches('tree_done'):
            self.log('已完成', module='发财树', reason='今日已完成砍树')
        else:
            rows = self.text((650, 630, 420, 200))
            free = next((p for t, p in rows if normalize(t) in ('免费', '免费砍树', '免费领取')), None)
            if free:
                self.tap(free, '发财树明确免费操作')
                self.wait('tree')
                self.log('已提交', module='发财树', verified=False)
            else:
                self.log('跳过', module='发财树', reason='没有明确的免费按钮，不消耗元宝')
        self.lobby()

    def finish(self):
        self.log('结束', frames=self.frames, local_ocr_calls=self.ocr_calls,
                 total_seconds=round(self.now() - self.started, 3))
        (self.folder / 'log.json').write_text(json.dumps(self.events, ensure_ascii=False, indent=2))
        if self.last is not None:
            self.last.save(self.folder / 'last.jpg', quality=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--module', choices=['scan', 'login', 'all', 'tasks', '军典', '节钺令', '发财树',
                                            '签到', '官阶', '活动', '武将抽取', '祈福', '公会'], default='scan')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.execute and args.module != 'scan':
        from sgs_login import ensure_game
        try:
            bot = ensure_game(FastDesktop, Bot, debug=args.debug)
        except Exception as error:
            print('登录停止：' + str(error), flush=True)
            return 1
    else:
        bot = Bot(FastDesktop(False), debug=args.debug)
    try:
        bot.snap()
        if not args.execute or args.module == 'scan':
            bot.log('只读扫描', pages=[name for name in ('lobby', 'task', 'military', 'scepter', 'tree')
                                     if bot.matches(name)])
        elif args.module == 'login':
            bot.log('仅登录完成，未运行领取')
        elif args.module == 'tasks':
            bot.task_bundle()
        elif args.module == 'all':
            bot.all()
        elif args.module == '公会':
            bot.guild()
        elif args.module == '发财树':
            bot.tree()
        elif args.module in ('军典', '节钺令'):
            bot.tasks_open()
            bot.passes(args.module)
            bot.lobby()
        else:
            bot.simple(args.module)
    except Exception as error:
        bot.log('停止', reason=str(error))
        return 1
    finally:
        bot.finish()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
