"""复用本机 Chrome 的 4399 登录状态，从官网进入 OL 后交给领取器。"""
import subprocess
import time
from collections import deque

PORTAL = 'https://my.4399.com/yxsgs/'


def enable_chrome_accessibility():
    # 终端启动时 Chrome 可能尚未生成网页辅助功能树。
    subprocess.run(['/usr/bin/osascript', '-e', '''
tell application "System Events" to tell process "Google Chrome"
    set value of attribute "AXEnhancedUserInterface" to true
end tell
'''], capture_output=True, timeout=5)


def portal_loading():
    result = subprocess.run(['/usr/bin/osascript', '-e', '''
tell application "Google Chrome"
    if (count of windows) is 0 then return "true"
    return loading of active tab of front window
end tell
'''], capture_output=True, text=True, timeout=5)
    return result.stdout.strip() == 'true'


def press_ol_link():
    """通过 Chrome 辅助功能树点击精确链接名，适应页面缩放和按钮配色。"""
    import ApplicationServices as ax
    from AppKit import NSWorkspace

    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if not front or front.bundleIdentifier() != 'com.google.Chrome':
        return False
    root = ax.AXUIElementCreateApplication(front.processIdentifier())
    ax.AXUIElementSetMessagingTimeout(root, 1.0)

    def attr(element, key):
        error, value = ax.AXUIElementCopyAttributeValue(element, key, None)
        return value if error == 0 else None

    window = attr(root, 'AXFocusedWindow')
    if window is None or '4399三国杀官网' not in str(attr(window, 'AXTitle') or ''):
        return False
    queue = deque([window])
    until = time.perf_counter() + 2
    while queue and time.perf_counter() < until:
        element = queue.popleft()
        if attr(element, 'AXRole') == 'AXLink':
            label = attr(element, 'AXTitle') or attr(element, 'AXDescription')
            if label == '三国杀OL':
                return ax.AXUIElementPerformAction(element, 'AXPress') == 0
        queue.extend(attr(element, 'AXChildren') or [])
    return False


def select_chrome_tab(kind):
    # 只读取标签标题，不读取、持久化带 token 的游戏跳转 URL。
    script = '''
on run argv
    set wanted to item 1 of argv
    tell application "Google Chrome"
        repeat with w in windows
            repeat with i from 1 to count of tabs of w
                set t to title of tab i of w
                if (wanted is "game" and t is "4399三国杀 三国杀OL") or (wanted is "portal" and t contains "4399三国杀官网") then
                    set active tab index of w to i
                    set index of w to 1
                    activate
                    return "found"
                end if
            end repeat
        end repeat
        if wanted is "portal" then
            if (count of windows) is 0 then make new window
            set newTab to make new tab at end of tabs of front window with properties {URL:"https://my.4399.com/yxsgs/"}
            set active tab index of front window to count of tabs of front window
            activate
            return "opened"
        end if
    end tell
    return "missing"
end run
'''
    result = subprocess.run(['/usr/bin/osascript', '-e', script, kind],
                            capture_output=True, text=True, timeout=12)
    if result.returncode:
        raise RuntimeError('无法控制 Chrome 标签页；请检查终端的自动化权限。')
    return result.stdout.strip()


def enter_portal(desktop_cls, bot_cls, debug=False):
    select_chrome_tab('portal')
    enable_chrome_accessibility()

    class PortalDesktop(desktop_cls):
        window_title = '4399三国杀官网'

    bot = bot_cls(PortalDesktop(True), debug=debug, deadline=180)
    notified = False
    attempts = 0
    next_click = 0
    try:
        end = bot.now() + 180
        while bot.now() < end:
            bot.d.wait_foreground(extra_titles=('4399三国杀 三国杀OL',))
            if select_chrome_tab('game') != 'missing':
                bot.log('游戏标签已确认')
                return
            bot.d.validate_window()  # 官网点击前也恢复默认缩放。
            if portal_loading() or bot.now() < next_click:
                time.sleep(.2)
                continue
            if attempts >= 3:
                bot.snap()
                raise RuntimeError('OL 入口已尝试三次但游戏标签未打开，请查看本次官网截图。')
            # 先读链接名；不依赖浏览器窗口大小、滚动位置或按钮悬停状态。
            try:
                pressed = press_ol_link()
            except ImportError:
                pressed = False
            if pressed:
                attempts += 1
                bot.log('点击', action='官网三国杀 OL 链接（辅助功能定位）', attempt=attempts)
                next_click = bot.now() + 4
                continue
            try:
                bot.snap()
            except RuntimeError as exc:
                # 页面刚打开时可能尚未形成带官网标题的窗口。
                if '未找到' not in str(exc):
                    raise
                time.sleep(.25)
                continue
            entry = bot.matches('portal_ol') or bot.matches('portal_ol_hover')
            if entry:
                bot.tap(entry[0], '官网开始游戏：三国杀 OL')
                attempts += 1
                bot.log('等待游戏标签确认', attempt=attempts)
                next_click = bot.now() + 4
                continue
            if not notified and bot.now() - bot.started > 8:
                print('正在自动定位 OL 入口并确认点击结果。若出现账号登录或验证码，请仅完成验证。', flush=True)
                notified = True
            time.sleep(.4)
        raise RuntimeError('官网入口未识别：请保持官网在页面顶部；已停止。')
    finally:
        bot.finish()


def ensure_game(desktop_cls, bot_cls, debug=False, force_portal=False):
    started = time.perf_counter()
    import Quartz
    import ApplicationServices as ax
    if not ax.AXIsProcessTrusted():
        raise RuntimeError('请在“系统设置→隐私与安全性→辅助功能”中允许“终端”（Terminal），再重新运行。')
    if hasattr(Quartz, 'CGPreflightScreenCaptureAccess') and not Quartz.CGPreflightScreenCaptureAccess():
        raise RuntimeError('请在“系统设置→隐私与安全性→屏幕与系统音频录制”中允许“终端”（Terminal），退出并重开终端后再运行。')
    if force_portal or select_chrome_tab('game') == 'missing':
        enter_portal(desktop_cls, bot_cls, debug)
    bot = bot_cls(desktop_cls(True), debug=debug, deadline=180)
    try:
        end = bot.now() + 120
        while bot.now() < end:
            bot.snap()
            if bot.dismiss():
                continue
            known_pages = ('lobby', 'task', 'welfare', 'rank', 'event', 'draw',
                           'blessing', 'guild_home', 'guild_drums', 'tree')
            if any(bot.matches(page) for page in known_pages):
                bot.lobby()
                bot.log('登录就绪', login_seconds=round(time.perf_counter() - started, 3))
                # 登录和领取分别计时、记录，登录等待不占领取的 90 秒上限。
                bot.finish()
                time.sleep(.01)
                ready = bot_cls(bot.d, debug=debug)
                ready.snap()
                return ready
            time.sleep(.25)
        raise RuntimeError('游戏加载超时或出现未适配页面，请查看结束截图。')
    except BaseException as error:
        bot.log('停止', reason=str(error))
        bot.finish()
        raise
