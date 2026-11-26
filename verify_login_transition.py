"""回归：OL 标签延迟获得标题时，不得再次等待官网窗口。"""
from unittest.mock import patch
from sgs_login import enter_portal

state = {'page': 'portal', 'polls': 0, 'clicks': 0}


class Desktop:
    def __init__(self, execute):
        pass

    def wait_foreground(self):
        assert state['page'] == 'portal', '游戏已打开，却又等待官网前台'

    def validate_window(self):
        assert state['page'] == 'portal', '游戏已打开，却又校验官网标题'


class Bot:
    def __init__(self, d, **kwargs):
        self.d = d
        self.started = self.now()

    def now(self):
        return 0

    def log(self, *args, **kwargs):
        pass

    def finish(self):
        pass

    def flush(self):
        pass


def select(kind):
    if kind == 'portal':
        return 'found'
    state['polls'] += 1
    # 新标签刚打开时没有最终标题，第二次才可定位。
    return 'found' if state['polls'] >= 2 else 'missing'


def click(**kwargs):
    state['clicks'] += 1
    state['page'] = 'game'
    return True


with patch('sgs_login.select_chrome_tab', side_effect=select), \
     patch('sgs_login.enable_chrome_accessibility'), \
     patch('sgs_login.portal_loading', return_value=False), \
     patch('sgs_login.press_ol_link', side_effect=click), \
     patch('sgs_login.time.sleep'):
    enter_portal(Desktop, Bot)
assert state['clicks'] == 1 and state['polls'] == 2
print('PASS 游戏新标签延迟就绪时，自动确认标签且不误暂停等待官网')
