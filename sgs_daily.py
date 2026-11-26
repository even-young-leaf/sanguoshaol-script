#!/usr/bin/env python3
"""三国杀 OL 免费奖励原型。macOS 本地 OCR；默认只观察。"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def normalize(text):
    return re.sub(r"[\s·:：,，。!！/\\|]", "", text)


class Desktop:
    def __init__(self, require_front=True):
        import pyautogui
        import Quartz
        import Vision
        from AppKit import NSWorkspace
        from Foundation import NSData
        self.pg, self.q, self.vision = pyautogui, Quartz, Vision
        self.workspace, self.data = NSWorkspace.sharedWorkspace(), NSData
        self.require_front = require_front
        self.pg.FAILSAFE = True
        self.pg.PAUSE = 0.3

    def focus_game(self):
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        windows = self.q.CGWindowListCopyWindowInfo(
            self.q.kCGWindowListOptionOnScreenOnly, self.q.kCGNullWindowID)
        window = next((w for w in windows if w.get("kCGWindowOwnerName") == "Google Chrome"
                       and w.get("kCGWindowLayer") == 0
                       and "4399三国杀 三国杀OL" in w.get("kCGWindowName", "")), None)
        if window is None:
            raise RuntimeError("请先在 Chrome 打开并登录三国杀 OL。")
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(window["kCGWindowOwnerPID"])
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        time.sleep(1)

    def capture(self):
        from PIL import Image
        front = self.workspace.frontmostApplication()
        if self.require_front and front.bundleIdentifier() != "com.google.Chrome":
            raise RuntimeError("请将 Chrome 的三国杀 OL 标签页放在最前方。")
        windows = self.q.CGWindowListCopyWindowInfo(
            self.q.kCGWindowListOptionOnScreenOnly, self.q.kCGNullWindowID)
        chrome = next((w for w in windows
                       if w.get("kCGWindowOwnerName") == "Google Chrome"
                       and w.get("kCGWindowLayer") == 0
                       and "4399三国杀 三国杀OL" in w.get("kCGWindowName", "")), None)
        if not chrome or "4399三国杀 三国杀OL" not in chrome.get("kCGWindowName", ""):
            raise RuntimeError("前台不是 4399 三国杀 OL 游戏窗口，停止。")
        b = chrome["kCGWindowBounds"]
        self.bounds = tuple(round(b[k]) for k in ("X", "Y", "Width", "Height"))
        x, y, w, h = self.bounds
        sw, sh = self.pg.size()
        if x < 0 or y < 0 or x + w > sw or y + h > sh:
            raise RuntimeError("请将游戏窗口完整放在主显示器内。")
        if self.require_front:
            top = next((win for win in windows
                        if win.get("kCGWindowOwnerPID") == front.processIdentifier()
                        and win.get("kCGWindowLayer") == 0
                        and win.get("kCGWindowBounds", {}).get("Width", 0) >= 300
                        and win.get("kCGWindowBounds", {}).get("Height", 0) >= 200), None)
            if not top or top["kCGWindowNumber"] != chrome["kCGWindowNumber"]:
                raise RuntimeError("游戏不是 Chrome 的最前窗口，停止。")
        # 只截取游戏窗口，即使观察时被其他应用遮挡也不会读到私人聊天。
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "window.png"
            subprocess.run(["/usr/sbin/screencapture", "-x", "-o", "-l",
                            str(chrome["kCGWindowNumber"]), str(path)],
                           check=True, timeout=10, capture_output=True)
            with Image.open(path) as shot:
                image = shot.convert("RGB")
                self.pixel_scale = (image.width / w, image.height / h)
                return image

    def read(self, image):
        import io
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        raw = stream.getvalue()
        data = self.data.dataWithBytes_length_(raw, len(raw))
        request = self.vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(self.vision.VNRequestTextRecognitionLevelAccurate)
        request.setRecognitionLanguages_(["zh-Hans", "en-US"])
        request.setUsesLanguageCorrection_(False)
        request.setMinimumTextHeight_(0.008)
        handler = self.vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise RuntimeError(f"OCR 失败：{error}")
        result = []
        for item in request.results() or []:
            candidates = item.topCandidates_(1)
            if not candidates:
                continue
            candidate, box = candidates[0], item.boundingBox()
            result.append({"text": str(candidate.string()),
                           "confidence": float(candidate.confidence()),
                           "box": [float(box.origin.x),
                                   float(1 - box.origin.y - box.size.height),
                                   float(box.size.width), float(box.size.height)]})
        return result

    def click(self, xy):
        # 再检查前台，避免将点击发给其他应用。
        if self.workspace.frontmostApplication().bundleIdentifier() != "com.google.Chrome":
            raise RuntimeError("前台应用已切换，停止。")
        previous = (self.bounds, self.pixel_scale)
        self.capture()
        if previous != (self.bounds, self.pixel_scale):
            raise RuntimeError("游戏窗口位置或尺寸发生变化，停止并重新识别。")
        x, y, _, _ = self.bounds
        self.pg.moveTo(x + xy[0] / self.pixel_scale[0],
                       y + xy[1] / self.pixel_scale[1], duration=0.2)
        self.pg.mouseDown()
        time.sleep(0.15)
        self.pg.mouseUp()

    def hover(self, xy):
        self.capture()  # 校验当前窗口位置、前台及缩放
        x, y, _, _ = self.bounds
        self.pg.moveTo(x + 400, y + 20, duration=0.1)
        time.sleep(0.3)
        self.pg.moveTo(x + xy[0] / self.pixel_scale[0],
                       y + xy[1] / self.pixel_scale[1], duration=0.2)
        time.sleep(0.9)


def center(item, size):
    x, y, w, h = item["box"]
    return ((x + w / 2) * size[0], (y + h / 2) * size[1])


def find_text(items, labels, region=(0, 0, 1, 1), confidence=0.7):
    targets = {normalize(s) for s in labels}
    x, y, w, h = region
    found = []
    for item in items:
        bx, by, bw, bh = item["box"]
        if (normalize(item["text"]) in targets and item["confidence"] >= confidence
                and x <= bx + bw / 2 <= x + w
                and y <= by + bh / 2 <= y + h):
            found.append(item)
    return found


def match_template(image, spec):
    """在限定区域内比对已实地确认的按钮，兼顾文字形状和颜色。"""
    import cv2
    import numpy as np
    from PIL import Image
    reference = image.resize(tuple(spec["reference_size"]), Image.Resampling.LANCZOS)
    pixels = np.array(reference.convert("RGB"))
    with Image.open(ROOT / spec["file"]) as im:
        target = np.array(im.convert("RGB"))
    rx, ry, rw, rh = spec["region"]
    h, w = pixels.shape[:2]
    ox, oy = int(rx * w), int(ry * h)
    region = pixels[oy:int((ry + rh) * h), ox:int((rx + rw) * w)]
    th, tw = target.shape[:2]
    if region.shape[0] < th or region.shape[1] < tw:
        return []
    scores = cv2.matchTemplate(cv2.cvtColor(region, cv2.COLOR_RGB2GRAY),
                               cv2.cvtColor(target, cv2.COLOR_RGB2GRAY),
                               cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    crop = region[y:y + th, x:x + tw]
    color_error = float(np.mean(np.abs(crop.astype(float) - target.astype(float))))
    if score < spec.get("threshold", 0.94) or color_error > spec.get("max_color_error", 22):
        return []
    return [{"text": spec.get("label", "已校准按钮"), "confidence": score,
             "box": [(ox + x) / w, (oy + y) / h, tw / w, th / h]}]


def red_dots(image, scale=1):
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (0, 140, 120), (9, 255, 255))
    mask |= cv2.inRange(hsv, (170, 140, 120), (180, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for contour in contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        x, y, w, h = cv2.boundingRect(contour)
        circularity = 4 * math.pi * area / (perimeter * perimeter) if perimeter else 0
        if (8 * scale <= w <= 26 * scale and 8 * scale <= h <= 26 * scale
                and 0.65 <= w / h <= 1.5 and circularity >= 0.65):
            out.append([x, y, w, h])
    return out


def has_red_dot(image, region, scale):
    rx, ry, rw, rh = region
    return any(rx <= (x + w / 2) / image.width <= rx + rw
               and ry <= (y + h / 2) / image.height <= ry + rh
               for x, y, w, h in red_dots(image, scale))


def free_count(items, spec):
    x, y, w, h = spec["region"]
    texts = []
    for item in items:
        bx, by, bw, bh = item["box"]
        if x <= bx + bw / 2 <= x + w and y <= by + bh / 2 <= y + h:
            texts.append(normalize(item["text"]))
    match = re.search(spec["pattern"], "".join(texts))
    if any(normalize(label) in "".join(texts) for label in spec.get("zero_labels", [])):
        return 0
    return int(match.group(1)) if match else None


class Runner:
    def __init__(self, desktop, execute=False):
        self.desktop, self.execute = desktop, execute
        self.folder = ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.folder.mkdir(parents=True)
        self.events, self.step = [], 0

    def log(self, status, **fields):
        event = {"time": datetime.now().isoformat(timespec="seconds"),
                 "status": status, **fields}
        self.events.append(event)
        print(json.dumps(event, ensure_ascii=False), flush=True)
        (self.folder / "log.json").write_text(
            json.dumps(self.events, ensure_ascii=False, indent=2), encoding="utf-8")

    def observe(self, label):
        from PIL import ImageDraw
        image = self.desktop.capture()
        items = self.desktop.read(image)
        self.step += 1
        stem = f"{self.step:03d}-{label}"
        image.save(self.folder / f"{stem}.png")
        (self.folder / f"{stem}.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        for i, item in enumerate(items):
            x, y, w, h = item["box"]
            x, w = x * image.width, w * image.width
            y, h = y * image.height, h * image.height
            draw.rectangle((x, y, x + w, y + h), outline="lime", width=1)
            draw.text((x, max(0, y - 10)), str(i), fill="lime")
        dots = red_dots(image, self.desktop.pixel_scale[0])
        for x, y, w, h in dots:
            draw.rectangle((x - 2, y - 2, x + w + 2, y + h + 2), outline="cyan", width=2)
        annotated.save(self.folder / f"{stem}-marked.png")
        self.log("观察", screen=label, red_dot_candidates=len(dots), text_count=len(items))
        return image, items

    def act(self, item, image, name):
        point = center(item, image.size)
        self.log("点击" if self.execute else "计划点击", action=name,
                 text=item["text"], point=list(map(round, point)))
        if self.execute:
            self.desktop.click(point)
            time.sleep(1.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scan", "run", "list"], nargs="?", default="scan")
    parser.add_argument("--execute", action="store_true", help="执行已配置并验证的流程")
    parser.add_argument("--module", default="签到", help="一次运行一个模块")
    parser.add_argument("--delay", type=int, default=5, help="切换到游戏窗口的倒计时")
    parser.add_argument("--focus", action="store_true", help="启动时将 Chrome 切到前台")
    args = parser.parse_args()
    if args.execute and args.command != "run":
        parser.error("--execute 只能与 run 一起使用")
    if args.command == "list":
        recipes = json.loads((ROOT / "recipes.json").read_text(encoding="utf-8"))
        for name, recipe in recipes.items():
            print(name, "可用" if recipe["enabled"] else recipe.get("reason", "尚未校准"))
        return 0
    print(f"{args.delay} 秒后开始，请切换到 Chrome 三国杀 OL。鼠标移至主屏左上角可中止。", flush=True)
    time.sleep(max(0, args.delay))
    runner = Runner(Desktop(require_front=args.execute), args.execute)
    try:
        if args.focus:
            runner.desktop.focus_game()
        if args.command == "scan":
            runner.observe("scan")
        else:
            for _ in range(12):
                if not run_module(runner, args.module):
                    break
    except Exception as exc:
        runner.log("停止", reason=str(exc))
        return 1
    print(f"记录目录：{runner.folder}")
    return 0


def run_module(runner, name):
    recipes = json.loads((ROOT / "recipes.json").read_text(encoding="utf-8"))
    if name not in recipes:
        raise RuntimeError(f"未知模块 {name}；可选：{'、'.join(recipes)}")
    recipe = recipes[name]
    if not recipe["enabled"]:
        raise RuntimeError(recipe.get("reason", f"{name} 尚未完成实际页面校准，保持禁用。"))
    image, items = runner.observe("start")
    # 运行从当前页面开始；只有能明确确认大厅时才尝试进入模块。
    if not page_matches(items, recipe):
        lobby = find_text(items, ["经典场"], [0.15, 0.3, 0.6, 0.4])
        if not lobby:
            raise RuntimeError("当前既不是该奖励页，也不是已识别的大厅，请手动打开奖励页后重试。")
        entries = find_text(items, recipe["entry_labels"], recipe["entry_region"])
        if len(entries) != 1:
            raise RuntimeError("入口不唯一或不可见；请先手动打开对应奖励页。")
        runner.act(entries[0], image, "进入" + name)
        if not runner.execute:
            runner.log("预览结束", note="观察模式不会进入下一页。")
            return
        image, items = runner.observe("entered")
        if not page_matches(items, recipe):
            raise RuntimeError("进入后未匹配预期页面，停止；可能需要选择子标签页。")

    done = find_text(items, recipe["done_labels"], recipe["action_region"])
    if recipe.get("done_template"):
        done += match_template(image, recipe["done_template"])
    if done:
        runner.log("已完成", module=name, evidence=[i["text"] for i in done])
        return
    if recipe.get("red_dot_region") and not has_red_dot(
            image, recipe["red_dot_region"], runner.desktop.pixel_scale[0]):
        runner.log("跳过", module=name, reason="对应奖励没有红点")
        return
    # 不做全屏通用领取；按钮、页面标题和区域必须同时匹配。
    buttons = find_text(items, recipe["action_labels"], recipe["action_region"])
    if not buttons and recipe.get("action_template"):
        buttons = match_template(image, recipe["action_template"])
    if len(buttons) > 1 and recipe.get("choose_first"):
        buttons = [min(buttons, key=lambda item: item["box"][1])]
    if len(buttons) != 1:
        runner.log("跳过", module=name, reason="未找到唯一的已配置免费按钮")
        return
    before_free = None
    if recipe.get("free_counter"):
        if not runner.execute:
            runner.log("预览结束", note="实际执行时会先悬停读取免费次数；此时尚未点击。")
            return
        runner.desktop.hover(center(buttons[0], image.size))
        image, items = runner.observe("free-check")
        before_free = free_count(items, recipe["free_counter"])
        if before_free is None or before_free <= 0:
            runner.log("跳过", module=name, reason="未识别到剩余免费次数大于零")
            return
        if not page_matches(items, recipe):
            raise RuntimeError("免费次数检查后页面发生变化")
    if recipe.get("free_guard_labels"):
        guards = find_text(items, recipe["free_guard_labels"], recipe["free_guard_region"],
                           recipe.get("free_guard_confidence", 0.7))
        if not guards:
            runner.log("跳过", module=name, reason="免费状态未确认")
            return
    if recipe.get("green_button"):
        import cv2
        import numpy as np
        cx, cy = center(buttons[0], image.size)
        crop = np.array(image.crop((cx - 90, cy - 30, cx + 90, cy + 30)).convert("RGB"))
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        green = cv2.inRange(hsv, (35, 70, 40), (95, 255, 255))
        if float(np.mean(green > 0)) < 0.2:
            runner.log("跳过", module=name, reason="领取按钮不是已校准的绿色状态")
            return
    before_count = len(find_text(items, recipe["action_labels"], recipe["action_region"]))
    runner.act(buttons[0], image, name + "免费领取")
    if not runner.execute:
        return
    action_point = center(buttons[0], image.size)
    # 每次点击后先验证结果，下一轮重新检查免费状态，不能直接连点。
    for attempt in range(recipe.get("verification_attempts", 5)):
        if recipe.get("free_counter"):
            runner.desktop.hover(action_point)
        image, items = runner.observe(f"after-{attempt}")
        if recipe.get("free_counter") and page_matches(items, recipe):
            remaining = free_count(items, recipe["free_counter"])
            if remaining is not None and remaining == before_free - 1:
                runner.log("领取已验证", module=name,
                           evidence=f"免费次数 {before_free} → {remaining}")
                return bool(recipe.get("repeat"))
        success = find_text(items, recipe["success_labels"], recipe["success_region"])
        done = (find_text(items, recipe["done_labels"], recipe["action_region"])
                if page_matches(items, recipe) else [])
        if page_matches(items, recipe) and recipe.get("done_template"):
            done += match_template(image, recipe["done_template"])
        if recipe.get("verify_count_drop") and page_matches(items, recipe):
            remaining = len(find_text(items, recipe["action_labels"], recipe["action_region"]))
            if remaining < before_count:
                runner.log("领取已验证", module=name,
                           evidence=f"当前页绿色领取按钮数量 {before_count} → {remaining}")
                return bool(recipe.get("repeat"))
        if recipe.get("verify_red_dot_gone") and page_matches(items, recipe):
            if not has_red_dot(image, recipe["red_dot_region"], runner.desktop.pixel_scale[0]):
                runner.log("领取已验证", module=name, evidence="对应奖励红点已消失")
                return bool(recipe.get("repeat"))
        if success or done:
            runner.log("领取已验证", module=name,
                       evidence=[i["text"] for i in success + done])
            return bool(recipe.get("repeat"))
        time.sleep(0.8)
    raise RuntimeError("已点击但无法验证奖励结果；请查看截图。不会再次点击或自动确认未知弹窗。")


def page_matches(items, recipe):
    return all(find_text(items, marker["labels"], marker["region"],
                         marker.get("confidence", 0.7))
               for marker in recipe["page_markers"])


if __name__ == "__main__":
    sys.exit(main())
