#!/usr/bin/env python3
"""三国杀 OL 快速巡检：缓存模板、局部 OCR、自动切页与关闭奖励。"""
from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from sgs_daily import Desktop, normalize, red_dots

ROOT = Path(__file__).resolve().parent
SIZE = (1657, 1079)


def is_continue_caption(text):
    text = normalize(text)
    if any(word in text for word in ('购买', '充值', '兑换', '抽取', '查看', '选择')):
        return False
    return bool(re.search(r'(?:点击|轻触|单击).{0,4}(?:任意(?:处|位置|地方|区域)|空白(?:处|位置|区域))', text)
                or re.search(r'点击屏幕.{0,3}(?:继续|关闭)', text))


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
        notified = False
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
                if not notified and time.perf_counter() - started >= .8:
                    print('已暂停：切回 Chrome 的游戏页面后自动继续；Ctrl+C 可结束。', flush=True)
                    notified = True
                time.sleep(.15)
        finally:
            if started is not None:
                duration = time.perf_counter() - started
                self.paused_seconds += duration
                self.focus_epoch = getattr(self, 'focus_epoch', 0) + 1
                if notified:
                    print(f'已等待 {duration:.1f} 秒，继续执行。', flush=True)

    def validate_window(self):
        while True:
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
                    continue
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
                    continue
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


    def __init__(self, desktop, debug=False, deadline=90, session=None, phase="巡检", keep_runs=20, tree_budget=150):
        self.d = desktop
        self.debug = debug
        self.started = self.now()
        self.deadline = self.started + deadline
        from sgs_runs import RunSession
        self.session = session or RunSession(keep=keep_runs)
        self.phase = phase
        self.events = self.session.events
        self.scaled_templates = {}
        self.tree_budget = tree_budget
        self.tree_ledger = None
        self.frames = 0
        self.ocr_calls = 0
        self.spec = json.loads((ROOT / 'templates_v2.json').read_text())
        self.templates = {}
        for key, spec in self.spec.items():
            self.templates[key] = cv2.cvtColor(np.array(Image.open(ROOT / spec['file']).convert('RGB')),
                                                cv2.COLOR_RGB2GRAY)
        self.folder = self.session.folder
        self.last = None

    def log(self, event, **values):
        row = {'elapsed_s': round(time.perf_counter() - self.session.started, 3), 'phase': self.phase, 'event': event, **values}
        self.events.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def snap(self, resolve_startup=True):
        if self.now() >= self.deadline:
            raise RuntimeError('超过本次运行时间上限，停止。')
        self.last = self.d.capture()
        self.frames += 1
        self.session.frames += 1
        if self.debug:
            self.last.save(self.folder / f'{self.session.frames:04d}.jpg', quality=80)
        if resolve_startup and getattr(self.d, 'execute', True):
            while self.dismiss_startup():
                pass
        return self.last

    def matches(self, name, image=None, region=None, threshold=.94, multiple=False):
        image = image if image is not None else self.last
        if name == 'startup_close':
            return self.startup_close_points(image)
        target = self.templates[name]
        x, y, w, h = region or self.spec[name]['region']
        crop = np.array(image.crop((x, y, x + w, y + h)).convert('RGB'))
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        th, tw = target.shape
        if h < th or w < tw:
            return self.scaled_matches(name, image, region, threshold, multiple)
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
        if points:
            return sorted(points, key=lambda p: (p[1], p[0]))
        found = self.scaled_matches(name, image, region, threshold, multiple)
        if not found and name in ('sign_done', 'experience_done', 'tree_done'):
            return self.matches(name + '_legacy', image=image, threshold=threshold, multiple=multiple)
        return found

    def scaled_matches(self, name, image, region, threshold, multiple):
        if name == 'draw':
            threshold = min(threshold, .92)  # 单独的招募页标题，字体栅格化有轻微差异。
        target = self.templates[name]
        x, y, w, h = region or self.spec[name]['region']
        x0, y0 = max(0, x - 30), max(120, y - 30)
        crop = image.crop((x0, y0, min(SIZE[0], x + w + 30), min(SIZE[1], y + h + 30)))
        gray = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
        best = None
        groups = ((1., .96, 1.04), (.92, .98, 1.02, 1.08), (.90, .94, 1.06, 1.10, .95, .97, .99, 1.01))
        for scales in groups:
            for scale in scales:
                key = (name, scale)
                if key not in self.scaled_templates:
                    self.scaled_templates[key] = cv2.resize(target, None, fx=scale, fy=scale)
                t = self.scaled_templates[key]
                th, tw = t.shape
                if th > gray.shape[0] or tw > gray.shape[1]:
                    continue
                scores = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
                _, score, _, loc = cv2.minMaxLoc(scores)
                if score < threshold or abs(float(gray[loc[1]:loc[1]+th, loc[0]:loc[0]+tw].mean()) - float(t.mean())) > 24:
                    continue
                if best is None or score > best[0]:
                    best = score, scores, tw, th, t
            if best is not None:
                break
        if best is None:
            return []
        _, scores, tw, th, t = best
        points = []
        for _ in range(24 if multiple else 1):
            _, score, _, loc = cv2.minMaxLoc(scores)
            if score < threshold:
                break
            lx, ly = loc
            if abs(float(gray[ly:ly+th, lx:lx+tw].mean()) - float(t.mean())) <= 24:
                points.append((x0 + lx + tw / 2, y0 + ly + th / 2))
            scores[max(0, ly-th//2):ly+th, max(0, lx-tw//2):lx+tw] = -1
        return sorted(points, key=lambda p: (p[1], p[0]))

    def startup_close_points(self, image):
        # 只匹配叉号和紧邻的轮播页码，不比较会轮换的宣传图片。
        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        x, y, w, h = 1150, 180, 390, 210
        area = gray[y:y + h, x:x + w]
        source = self.templates['startup_close']
        candidates = []
        for scale in (.8, .85, .9, .95, 1., 1.05, 1.1, 1.15, 1.2):
            target = cv2.resize(source, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            th, tw = target.shape
            scores = cv2.matchTemplate(area, target, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(scores)
            if score < .85:
                continue
            px, py = x + loc[0] + tw / 2, y + loc[1] + th / 2
            # 宣传页在叉号左下方有一行至少三个红色方形轮播页码。
            box = (int(px - 175 * scale), int(py + 8 * scale),
                   int(px + 15 * scale), int(py + 68 * scale))
            hsv = cv2.cvtColor(np.array(image.crop(box)), cv2.COLOR_RGB2HSV)
            red = (((hsv[:, :, 0] < 13) | (hsv[:, :, 0] > 170))
                   & (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 45)).astype('uint8') * 255
            contours, _ = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            squares = [cv2.boundingRect(c) for c in contours]
            squares = [(a, b, cw, ch) for a, b, cw, ch in squares
                       if 12 * scale < cw < 42 * scale and 12 * scale < ch < 42 * scale
                       and .65 < cw / ch < 1.5]
            if len(squares) >= 3:
                centers = [b + ch / 2 for _, b, _, ch in squares]
                if max(centers) - min(centers) < 10 * scale:
                    candidates.append((score, (px, py)))
        return [max(candidates, key=lambda row: row[0])[1]] if candidates else []

    def dot(self, box):
        x, y, w, h = box
        im = self.last.crop((x, y, x + w, y + h))
        return bool(red_dots(im, 1))

    def text(self, box):
        self.ocr_calls += 1
        self.session.ocr_calls += 1
        x, y, w, h = box
        crop = self.last.crop((x, y, x + w, y + h))
        # 局部 OCR 不缩小汉字；识别坐标映射回窗口。
        rows = self.d.read(crop.resize((w * 2, h * 2), Image.Resampling.BILINEAR))
        return [(r['text'], (x + (r['box'][0] + r['box'][2] / 2) * w,
                            y + (r['box'][1] + r['box'][3] / 2) * h)) for r in rows]

    def tap(self, point, action):
        # 点击前再次排除延迟弹出的宣传遮挡。
        self.snap()
        self.log('点击', action=action)
        self.d.tap(point)

    def dismiss_startup(self):
        if not getattr(self.d, 'execute', True):
            return False
        # 宣传页可能在登录后延迟出现，所有页面等待都需要处理。
        close = self.matches('startup_close')
        if close:
            self.startup_close_attempts = getattr(self, 'startup_close_attempts', 0) + 1
            if self.startup_close_attempts > 5:
                raise RuntimeError('活动宣传页连续五次未能关闭，已停止并保存截图。')
            self.log('点击', action='关闭活动宣传弹窗')
            self.d.tap(close[0])
            time.sleep(.2)
            self.snap(resolve_startup=False)
            if not self.matches('startup_close'):
                self.log('宣传弹窗关闭已确认')
                self.startup_close_attempts = 0
            return True
        self.startup_close_attempts = 0
        return False

    def dismiss_continue(self):
        if not getattr(self.d, 'execute', True):
            return False
        if self.now() - getattr(self, '_caption_checked_at', float('-inf')) < .3:
            return False
        self._caption_checked_at = self.now()
        rows = self.text((300, 620, 1080, 430))
        found = next(((text, point) for text, point in rows if is_continue_caption(text)), None)
        if not found:
            self._continuation_tries = 0
            return False
        self._continuation_tries = getattr(self, '_continuation_tries', 0) + 1
        if self._continuation_tries > 4:
            raise RuntimeError('奖励页继续提示多次点击后仍未退出，已保存画面。')
        self.tap(found[1], '按奖励提示继续或退出：' + found[0])
        time.sleep(.1)
        self.snap()
        self.log('奖励继续提示已处理')
        return True

    def dismiss(self, include_continue=False):
        if not getattr(self.d, 'execute', True):
            return False
        if self.dismiss_startup():
            return True
        # 奖励标题模板已知时，仅在前景标题出现后点击预先核对过的空白区域。
        if 'reward' in self.templates and self.matches('reward'):
            self.tap((1320, 790), '关闭奖励弹窗')
            return True
        if self.matches('experience_done'):
            return False  # 提示条不阻挡页面
        return self.dismiss_continue() if include_continue else False

    def wait(self, anchor, timeout=3):
        end = self.now() + timeout
        while self.now() < end:
            self.snap()
            if self.dismiss():
                continue
            if self.matches(anchor):
                return self.last
            if self.dismiss_continue():
                continue
            time.sleep(.035)
        raise RuntimeError(f'页面未就绪：{anchor}。已保存最后画面，未继续盲点。')

    def navigate(self, point, anchor, name):
        self.tap(point, name)
        return self.wait(anchor)

    def lobby(self):
        for _ in range(7):
            self.snap()
            if self.dismiss(include_continue=True):
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
                name, point = match
                if name != 'blessing':
                    x, y = point
                    found = self.scaled_matches('startup_close', self.last, (x - 25, y - 25, 50, 50), .85, False)
                    if not found:
                        raise RuntimeError(f'{name} 页已识别，但没有定位到关闭叉号。')
                    point = found[0]
                self.tap(point, '返回大厅：' + name)
                time.sleep(.08)
            else:
                raise RuntimeError('当前有未适配的页面或弹窗；请返回大厅后重试。')
        raise RuntimeError('未能返回大厅。')

    def tasks_open(self):
        self.open_side('任务', 'task', '打开任务')

    def open_side(self, label, anchor, action):
        self.lobby()
        for _ in range(3):
            self.snap()
            rows = self.text((0, 160, 115, 850))
            target = next((point for text, point in rows if normalize(text).strip('.,。:：') == label), None)
            if target:
                return self.navigate(target, anchor, action)
            toggle = next((point for text, point in rows if normalize(text).strip('.,。:：') in ('展开', '收起')), None)
            if toggle is None:
                self.log('侧栏识别重试', labels=[text for text, _ in rows])
                time.sleep(.15)  # 返回大厅的淡入动画结束后重新读取侧栏。
                continue
            self.tap(toggle, '展开或切换左侧入口')
            self.d.move((800, 180))  # 离开侧栏，避免悬停在底部导致菜单继续滚动。
            time.sleep(.15)
        raise RuntimeError(f'左侧没有识别到“{label}”入口，已保存画面。')

    def reward_result(self, anchor, timeout=2, verify=None):
        end = self.now() + timeout
        overlay = False
        while self.now() < end:
            self.snap()
            if 'reward' in self.templates and self.matches('reward'):
                self.log('奖励弹窗已确认')
                self.dismiss()
                overlay = True
                continue
            if self.dismiss_continue():
                overlay = True
                continue
            if self.matches(anchor):
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
        self.tap(found[0], module + '一键领取（不购买通行证）')
        verified = self.reward_result(anchor, verify=lambda: not self.dot(dot_box))
        self.log('模块完成', module=module, verified=verified)

    def green_claims(self, anchor, region, pages=1):
        confirmed = 0
        for page in range(pages):
            self.wait(anchor)
            for _ in range(16):
                buttons = self.claim_buttons(region)
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
                self.tap(point, '领取当前已完成的免费任务奖励')
                if not self.reward_result(anchor,
                                          verify=lambda: not self.claim_buttons(box)):
                    break
                confirmed += 1
                self.wait(anchor)
            if page + 1 < pages:
                self.d.scroll((1250, 760), -12)
                time.sleep(.06)
        return confirmed

    def claim_buttons(self, region):
        found = []
        for template in ('green_claim', 'task_claim'):
            if template not in self.templates:
                continue
            for point in self.matches(template, region=region, threshold=.93, multiple=True):
                if any(abs(point[0]-p[0]) < 12 and abs(point[1]-p[1]) < 12 for p in found):
                    continue
                sample = np.array(self.last.crop((point[0]-45, point[1]-14, point[0]+45, point[1]+14)))
                hsv = cv2.cvtColor(sample, cv2.COLOR_RGB2HSV)
                if np.mean(cv2.inRange(hsv, (35, 70, 40), (95, 255, 255)) > 0) >= .20:
                    found.append(point)
        return sorted(found, key=lambda p: (p[1], p[0]))

    def task_silver(self):
        self.wait('task')
        rows = self.text((650, 425, 740, 55))
        eligible = []
        for text, point in rows:
            match = (re.fullmatch(r'\s*(\d+)\s*[/／]\s*(3|6|9)\s*', text)
                     or re.fullmatch(r'\s*(\d{1,2})[1Il|](3|6|9)\s*', text))
            if match and int(match[1]) >= int(match[2]):
                eligible.append((int(match[2]), (point[0], point[1]-45)))
        for threshold, point in eligible:
            if self.task_silver_done(point):
                self.log('任务银两已领取', threshold=threshold)
                continue
            self.tap(point, f'领取完成{threshold}项任务的银两奖励')
            self.d.move((800, 180))
            verified = self.reward_result('task', timeout=3, verify=lambda: self.task_silver_done(point))
            self.log('任务银两领取', threshold=threshold, verified=verified)
            self.wait('task')

    def task_silver_done(self, point):
        x, y = point
        image = np.array(self.last.crop((x-45, y-45, x+45, y+40)))
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        red = (((hsv[:, :, 0] < 10) | (hsv[:, :, 0] > 170))
               & (hsv[:, :, 1] > 130) & (hsv[:, :, 2] > 100))
        return np.mean(red) > .02  # 银两图标本身为灰色；领取后覆盖红色“已领取”印章。

    def activity_rewards(self):
        self.open_side('活动', 'event', '打开活动')
        for label in ('充消返利', '活跃福利', '限时活动'):
            rows = self.text((240, 280, 185, 580))
            point = next((p for text, p in rows if normalize(text).strip('.,。:：') == label), None)
            if point is None:
                self.log('活动页未适配', tab=label)
                continue
            self.tap(point, '打开活动页：' + label)
            self.d.move((800, 180))
            time.sleep(.2)
            self.wait('event')
            if label == '充消返利':
                rows = self.text((850, 380, 350, 150))
                free = next((p for text, p in rows if '免费好礼' in text), None)
                if free is None:
                    self.log('跳过', module='活动', tab=label, reason='未确认免费好礼行')
                    continue
                region = (1150, int(free[1] + 10), 220, 105)
                count = self.green_claims('event', region)
            else:
                # 仅已适配的任务型活动；不进入礼包、兑换、抽取等活动页。
                count = self.green_claims('event', (1150, 380, 220, 490), pages=4)
            self.log('活动页检查完成', tab=label, confirmed_rewards=count)
        self.lobby()

    def task_bundle(self):
        self.tasks_open()
        self.navigate((318, 390), 'experience', '打开我要强将')
        self.tap(self.matches('experience')[0], '领取每日体验卡')
        end = self.now() + 1
        while self.now() < end:
            self.snap()
            if self.matches('experience_done') or self.matches('reward'):
                break
            time.sleep(.02)
        if self.matches('experience_done'):
            self.log('已完成', module='每日体验卡', reason='今日已获得过体验卡')
        elif self.dismiss(include_continue=True):
            self.log('奖励已确认', module='每日体验卡')
        else:
            text = ''.join(normalize(t) for t, _ in self.text((600, 520, 500, 150)))
            if '体验卡' in text and ('已获得' in text or '获得过' in text):
                self.log('已完成', module='每日体验卡', reason='提示今日已获得过体验卡')
            else:
                self.log('已提交', module='每日体验卡', verified=False)
        self.navigate((622, 315), 'ascension', '切换羽化飞升')
        self.green_claims('ascension', (1185, 340, 162, 530), pages=6)
        self.log('模块完成', module='羽化飞升', note='只查领取按钮，跳过兑换、前往及未完成项')
        self.navigate((318, 452), 'task', '切换日常任务')
        count = self.green_claims('task', (1150, 470, 220, 440), pages=6)
        self.log('日常任务领取完成', confirmed_rewards=count)
        self.task_silver()
        for module in ('军典', '节钺令'):
            self.passes(module)
        self.lobby()

    def simple(self, module):
        if module == '签到':
            self.open_side('福利', 'welfare', '打开福利签到')
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
                    self.tap(points[0], '今日免费签到')
                    ok = self.reward_result('welfare',
                                             verify=lambda: bool(self.matches('sign_done')))
                    self.log('模块完成', module=module, verified=ok)
                else:
                    self.log('跳过', module=module, reason='没有今日免费签到按钮')
        elif module == '官阶':
            self.lobby()
            self.navigate((1426, 1048), 'rank', '打开官阶')
            points = self.matches('rank_claim')
            box = (int(points[0][0] + 15), int(points[0][1] - 75), 70, 70) if points else None
            if points and self.dot(box):
                self.tap(points[0], '免费每日俸禄')
                ok = self.reward_result('rank',
                                         verify=lambda: not self.dot(box))
                self.log('模块完成', module=module, verified=ok)
            else:
                self.log('跳过', module=module, reason='没有待领取俸禄红点')
        elif module == '活动':
            self.activity_rewards()
        elif module == '武将抽取':
            self.lobby()
            self.navigate((1528, 1048), 'draw', '打开招募')
            box = (768, 781, 27, 32)
            if self.dot(box):
                if not any(normalize(t) == '免费开启' for t, _ in self.text((665, 900, 160, 65))):
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
            self.open_side('祈福', 'blessing', '打开祈福')
            free = self.matches('blessing_free')
            if free and self.dot((749, 918, 29, 29)):
                self.tap(free[0], '免费祈福')
                # 动画期间免费按钮也会消失，必须等到真实奖励弹窗。
                ok = self.reward_result('blessing', timeout=12)
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

    def tree_drops(self):
        if not self.matches('tree') or self.matches('tree_price_150') or self.matches('tree_done'):
            return []
        found = []
        for name in ('tree_drop', 'tree_drop_alt'):
            for point in self.matches(name, threshold=.88, multiple=True):
                if not any(abs(point[0]-p[0]) < 25 and abs(point[1]-p[1]) < 20 for p in found):
                    found.append(point)
        if len(found) < 2 and not getattr(self, '_tree_collecting', False):
            return []
        return sorted(found, key=lambda p: (p[1], p[0]))

    def tree_result(self, allow_paid_confirmation=False):
        end = self.now() + 20
        confirmed_prompt = False
        while self.now() < end:
            self.snap()
            if self.matches('tree_done'):
                return True
            drops = self.tree_drops()
            if drops:
                self._tree_collecting = True
                self.tap(drops[0], '拾取发财树掉落的元宝')
                time.sleep(.12)
                continue
            rows = self.text((450, 380, 850, 410))
            words = ''.join(normalize(text) for text, _ in rows)
            prices = re.findall(r'(\d+)元宝', words)
            confirm = next((point for text, point in rows if normalize(text) in ('确定', '确认')), None)
            if (not confirmed_prompt and confirm and ('砍树' in words or '发财树' in words)
                    and prices and set(prices) == {'150'}):
                if not allow_paid_confirmation or self.tree_budget < 150:
                    cancel = next((point for text, point in rows if normalize(text) == '取消'), None)
                    if cancel:
                        self.tap(cancel, '取消未经授权的发财树付费确认')
                    self.log('未验证', module='发财树', reason='本分支未授权150元宝确认')
                    return False
                self.tap(confirm, '确认仅消耗150元宝砍树')
                confirmed_prompt = True
                continue
            if self.dismiss(include_continue=True):
                continue
            if '今日已完成砍树' in words:
                return True
            time.sleep(.12)
        self.log('未验证', module='发财树', reason='结果未确认；本日不会重复支出150元宝')
        return False

    def tree(self):
        self.lobby()
        self.tap((1628, 1048), '打开更多菜单')
        self.wait('tree_entry')
        self.navigate(self.matches('tree_entry')[0], 'tree', '进入发财树')
        self._tree_collecting = False
        try:
            if self.matches('tree_done'):
                from sgs_tree import TreeSpendLedger
                (self.tree_ledger or TreeSpendLedger()).confirm()
                self.log('已完成', module='发财树', reason='今日已完成砍树')
                return
            if self.tree_drops():
                from sgs_tree import TreeSpendLedger
                self.tree_ledger = self.tree_ledger or TreeSpendLedger()
                verified = self.tree_result()
                if verified:
                    self.tree_ledger.confirm()
                self.log('继续拾取发财树奖励', additional_yuanbao_budget=0, verified=verified)
                return
            rows = self.text((650, 630, 420, 200))
            free = next((point for text, point in rows if normalize(text) in ('免费', '免费砍树', '免费领取')), None)
            if free:
                self.tap(free, '发财树明确免费操作')
                self.log('发财树领取', yuanbao_budget=0, verified=self.tree_result())
                return
            price = [normalize(text) for text, _ in self.text((780, 735, 150, 60))]
            if '150' not in price:
                self.log('跳过', module='发财树', reason='未确认免费按钮或150元宝价格')
                return
            if self.tree_budget < 150:
                self.log('跳过', module='发财树', reason='当前砍树标价150元宝，预算为0，不消费')
                return
            price_marker = self.matches('tree_price_150')
            if not price_marker:
                self.log('跳过', module='发财树', reason='未确认150元宝价格图标，不消费')
                return
            if self.tree_ledger is None:
                from sgs_tree import TreeSpendLedger
                self.tree_ledger = TreeSpendLedger()
            if not self.tree_ledger.reserve():
                self.log('跳过', module='发财树', reason='今日已请求过150元宝砍树，不重复消费')
                return
            px, py = price_marker[0]
            self.tap((px - 35, py - 95), '发财树砍树：本日上限150元宝')
            verified = self.tree_result(allow_paid_confirmation=True)
            if verified:
                self.tree_ledger.confirm()
            self.log('发财树领取', yuanbao_budget=150, verified=verified)
        finally:
            self.lobby()

    def flush(self):
        self.session.flush(self.last)

    def finish(self):
        if self.session.finished:
            return
        self.log('结束', frames=self.session.frames, local_ocr_calls=self.session.ocr_calls,
                 total_seconds=round(time.perf_counter() - self.session.started, 3))
        self.flush()
        self.session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--module', choices=['scan', 'login', 'all', 'tasks', '军典', '节钺令', '发财树',
                                            '签到', '官阶', '活动', '武将抽取', '祈福', '公会'], default='scan')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--keep-runs', type=int, default=20, help='保留最近 N 次运行日志，默认 20')
    parser.add_argument('--tree-budget', type=int, choices=(0, 150), default=150, help='发财树每日元宝预算，默认150，0禁用付费砍树')
    args = parser.parse_args()
    if args.keep_runs < 1:
        parser.error('--keep-runs 必须大于 0')
    if args.execute and args.module != 'scan':
        from sgs_login import ensure_game
        try:
            bot = ensure_game(FastDesktop, Bot, debug=args.debug, keep_runs=args.keep_runs)
        except Exception as error:
            print('登录停止：' + str(error), flush=True)
            return 1
    else:
        bot = Bot(FastDesktop(False), debug=args.debug, keep_runs=args.keep_runs)
    bot.tree_budget = args.tree_budget
    try:
        bot.snap()
        if not args.execute or args.module == 'scan':
            bot.log('只读扫描', pages=[name for name in ('lobby', 'task', 'military', 'scepter', 'tree')
                                     if bot.matches(name)], startup_popup=bool(bot.matches('startup_close')))
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
