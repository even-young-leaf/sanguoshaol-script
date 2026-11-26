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


def press_ol_link(physical=False):
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
                if physical:
                    import Quartz as q
                    position, size = attr(element, 'AXPosition'), attr(element, 'AXSize')
                    if position is None or size is None:
                        return False
                    ok1, point = ax.AXValueGetValue(position, ax.kAXValueCGPointType, None)
                    ok2, dimensions = ax.AXValueGetValue(size, ax.kAXValueCGSizeType, None)
                    if not ok1 or not ok2:
                        return False
                    center = (point.x + dimensions.width / 2, point.y + dimensions.height / 2)
                    for kind in (q.kCGEventMouseMoved, q.kCGEventLeftMouseDown):
                        q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateMouseEvent(None, kind, center, q.kCGMouseButtonLeft))
                    time.sleep(.06)
                    q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseUp, center, q.kCGMouseButtonLeft))
                    return True
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
                if (wanted is "game" and t contains "4399三国杀 三国杀OL") or (wanted is "portal" and t contains "4399三国杀官网") then
                    set active tab index of w to i
                    set minimized of w to false
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


def enter_portal(desktop_cls, bot_cls, debug=False, session=None):
    select_chrome_tab('portal')
    enable_chrome_accessibility()

    class PortalDesktop(desktop_cls):
        window_title = '4399三国杀官网'

    bot = bot_cls(PortalDesktop(True), debug=debug, deadline=180, session=session, phase="登录-官网")
    notified = False
    attempts = 0
    next_click = 0
    try:
        end = bot.now() + 180
        while bot.now() < end:
            # 点击后只等待新游戏标签，不能再用官网标题校验新页面。
            # 否则游戏恰好在两次检查之间打开，会永远等“官网回到前台”。
            if attempts:
                if select_chrome_tab('game') != 'missing':
                    bot.log('游戏标签已确认')
                    return
                if bot.now() < next_click:
                    time.sleep(.2)
                    continue
                if attempts >= 3:
                    raise RuntimeError('OL 入口已尝试三次但游戏标签未打开，请检查浏览器登录或弹窗拦截提示。')
                select_chrome_tab('portal')
            bot.d.wait_foreground()
            if portal_loading():
                time.sleep(.2)
                continue
            bot.d.validate_window()  # 仅在准备点击官网入口时校验官网。
            # 先读链接名；不依赖浏览器窗口大小、滚动位置或按钮悬停状态。
            try:
                pressed = press_ol_link(physical=attempts > 0)
            except ImportError:
                pressed = False
            if pressed:
                attempts += 1
                bot.log('点击', action='官网三国杀 OL 链接（辅助功能定位）', attempt=attempts)
                next_click = bot.now() + 8
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
                next_click = bot.now() + 8
                continue
            if not notified and bot.now() - bot.started > 8:
                print('正在自动定位 OL 入口并确认点击结果。若出现账号登录或验证码，请仅完成验证。', flush=True)
                notified = True
            time.sleep(.4)
        raise RuntimeError('官网入口未识别：请保持官网在页面顶部；已停止。')
    except BaseException as error:
        bot.log('停止', reason=str(error))
        bot.finish()
        raise
    finally:
        bot.flush()


def ensure_game(desktop_cls, bot_cls, debug=False, force_portal=False, keep_runs=20):
    started = time.perf_counter()
    import Quartz
    import ApplicationServices as ax
    if not ax.AXIsProcessTrusted():
        raise RuntimeError('请在“系统设置→隐私与安全性→辅助功能”中允许“终端”（Terminal），再重新运行。')
    if hasattr(Quartz, 'CGPreflightScreenCaptureAccess') and not Quartz.CGPreflightScreenCaptureAccess():
        raise RuntimeError('请在“系统设置→隐私与安全性→屏幕与系统音频录制”中允许“终端”（Terminal），退出并重开终端后再运行。')
    from sgs_runs import RunSession
    session = RunSession(keep=keep_runs)
    if force_portal or select_chrome_tab('game') == 'missing':
        enter_portal(desktop_cls, bot_cls, debug, session=session)
    bot = bot_cls(desktop_cls(True), debug=debug, deadline=180, session=session, phase='登录-游戏')
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
                bot.flush()
                bot.phase = '巡检'
                bot.started = bot.now()
                bot.deadline = bot.started + 90
                return bot
            time.sleep(.25)
        raise RuntimeError('游戏加载超时或出现未适配页面，请查看结束截图。')
    except BaseException as error:
        bot.log('停止', reason=str(error))
        bot.finish()
        raise
