"""离线验证应用切换期间没有鼠标事件，恢复后继续且不消耗任务超时。"""
from types import SimpleNamespace as S
from unittest.mock import patch
from sgs_fast import FastDesktop, Bot


def desktop(background_tab=False):
    state = {'time': 0.0, 'events': [], 'polls': 0}
    chrome = S(bundleIdentifier=lambda: 'com.google.Chrome', processIdentifier=lambda: 7)
    other = S(bundleIdentifier=lambda: 'com.example.Other', processIdentifier=lambda: 8)
    win = dict(kCGWindowOwnerName='Google Chrome', kCGWindowOwnerPID=7,
               kCGWindowName='4399三国杀 三国杀OL', kCGWindowLayer=0,
               kCGWindowNumber=1, kCGWindowBounds=dict(X=0, Y=0, Width=1657, Height=1079))
    def windows(*args):
        state['polls'] += 1
        current = dict(win)
        if background_tab and state['time'] < 4:
            current['kCGWindowName'] = 'New Tab'
        return [current]
    def front():
        return chrome if background_tab or state['time'] >= 4 else other
    def sleep(seconds):
        if state['time'] < 4:
            assert not state['events'], '后台期间不能发送鼠标事件'
        state['time'] += seconds
    q = S(CGWindowListCopyWindowInfo=windows, kCGWindowListOptionOnScreenOnly=1,
          CGDisplayBounds=lambda _: S(size=S(width=2000, height=1200)), CGMainDisplayID=lambda: 0,
          CGEventGetLocation=lambda _: S(x=20, y=20), CGEventCreate=lambda _: None,
          kCGEventMouseMoved=1, kCGEventLeftMouseDown=2, kCGEventLeftMouseUp=3,
          kCGMouseButtonLeft=0, kCGHIDEventTap=0,
          CGEventCreateMouseEvent=lambda _, kind, pos, button: kind,
          CGEventPost=lambda _, event: state['events'].append(event))
    d = FastDesktop.__new__(FastDesktop)
    d.q, d.workspace = q, S(frontmostApplication=front)
    d.require_front = d.execute = True
    d.paused_seconds = 0
    d.zoom_guard = S(ensure=lambda: False)
    return d, state, sleep


for tab in (False, True):
    d, state, sleep = desktop(tab)
    with patch('sgs_fast.time.perf_counter', side_effect=lambda: state['time']), \
         patch('sgs_fast.time.sleep', side_effect=sleep):
        before = d.active_time()
        d.tap((100, 100))
        assert state['events'] == [1, 2, 3]
        assert d.paused_seconds >= 4
        assert d.active_time() - before < .1
    print('PASS', '切换浏览器标签' if tab else '切换其他应用', '暂停后恢复且后台不点击')

d, state, sleep = desktop()
bot = Bot.__new__(Bot)
bot.d, bot.last = d, None
bot.snap = lambda: d.wait_foreground()
bot.matches = lambda _: True
bot.dismiss = lambda: False
with patch('sgs_fast.time.perf_counter', side_effect=lambda: state['time']), \
     patch('sgs_fast.time.sleep', side_effect=sleep):
    bot.wait('lobby', timeout=1)
    assert state['time'] >= 4
    assert bot.now() < 1
print('PASS 暂停四秒不耗尽一秒页面等待时限')
