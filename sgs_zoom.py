"""读取 Chrome 地址栏的实际缩放百分比，自动恢复校准比例。"""
import re
import time
from collections import deque


class ZoomGuard:
    def __init__(self, desktop):
        import ApplicationServices as ax
        self.ax = ax
        self.desktop = desktop
        # 使用已核对的游戏窗口 PID，避免控制到其他前台应用。
        self.root = ax.AXUIElementCreateApplication(desktop.owner_pid)
        ax.AXUIElementSetMessagingTimeout(self.root, .5)

    def attr(self, element, key):
        error, value = self.ax.AXUIElementCopyAttributeValue(element, key, None)
        return value if error == 0 else None

    def level(self):
        window = self.attr(self.root, 'AXFocusedWindow')
        if window is None:
            raise RuntimeError('无法读取 Chrome 缩放状态，请检查辅助功能权限。')
        queue = deque([window])
        toolbar = address = False
        for _ in range(160):
            if not queue:
                break
            element = queue.popleft()
            role = self.attr(element, 'AXRole')
            if role in ('AXWebArea', 'AXMenuBar'):
                continue  # 不读取网页、账号和地址栏中的 URL。
            toolbar |= role == 'AXToolbar'
            address |= role == 'AXTextField'
            if role == 'AXButton':
                label = str(self.attr(element, 'AXTitle') or self.attr(element, 'AXDescription') or '')
                match = re.search(r'(?:Zoom|缩放)[^\d]*(\d+)\s*%', label, re.I)
                if match:
                    self.zoom_button = element
                    return int(match.group(1))
            queue.extend(self.attr(element, 'AXChildren') or [])
        # Chrome 在 100% 时隐藏地址栏缩放按钮。
        if toolbar and address:
            return 100
        raise RuntimeError('未能读取 Chrome 地址栏缩放状态，未继续点击。')

    def nondefault(self):
        return self.level() != 100

    def ensure(self):
        current = self.level()
        if current == 100:
            return False
        print(f'检测到页面缩放 {current}%，正在自动恢复为 100%。', flush=True)
        if self.ax.AXUIElementPerformAction(self.zoom_button, 'AXPress'):
            raise RuntimeError('无法打开 Chrome 缩放控件，未继续点击。')
        reset = None
        end = time.perf_counter() + 2
        while time.perf_counter() < end and reset is None:
            queue = deque(self.attr(self.root, 'AXWindows') or [])
            for _ in range(240):
                if not queue:
                    break
                element = queue.popleft()
                role = self.attr(element, 'AXRole')
                if role == 'AXWebArea':
                    continue
                label = self.attr(element, 'AXTitle') or self.attr(element, 'AXDescription')
                if role == 'AXButton' and label in ('Reset', '重置'):
                    reset = element
                    break
                queue.extend(self.attr(element, 'AXChildren') or [])
            if reset is None:
                time.sleep(.03)
        if reset is None or self.ax.AXUIElementPerformAction(reset, 'AXPress'):
            raise RuntimeError('未找到可用的浏览器缩放重置按钮，未继续点击。')
        # 点击同一个地址栏缩放控件收起气泡，避免覆盖游戏。
        self.ax.AXUIElementPerformAction(self.zoom_button, 'AXPress')
        end = time.perf_counter() + 2
        while time.perf_counter() < end:
            if not self.nondefault():
                time.sleep(.2)
                print('已确认页面缩放为 100%。', flush=True)
                return True
            time.sleep(.05)
        raise RuntimeError('未能恢复页面缩放为 100%，已停止且未继续点击。')
