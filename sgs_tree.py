"""发财树每日150元宝上限；请求先落盘，结果不明时禁止重复消费。"""
import fcntl
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class TreeSpendLedger:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).resolve().parent / '.tree-spend.json'

    def update(self, confirm=False, day=None):
        day = day or datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            record = json.loads(self.path.read_text()) if self.path.exists() else {}
            if confirm:
                if record.get('day') != day or record.get('status') != 'pending':
                    return False
                record['status'] = 'confirmed'
            else:
                if record.get('day') == day:
                    return False
                record = {'day': day, 'yuanbao': 150, 'status': 'pending'}
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            tmp.replace(self.path)
            return True

    def reserve(self, day=None):
        return self.update(day=day)

    def confirm(self, day=None):
        return self.update(confirm=True, day=day)
