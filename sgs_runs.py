"""一次启动共用一份日志，默认保留最近 20 次；不删除仍在运行的目录。"""
import fcntl
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path


def prune_runs(root, keep, current=None):
    if keep < 1:
        raise ValueError('keep 必须大于 0')
    folders = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                      and re.fullmatch(r'\d{8}-\d{6}(?:-\d{6})?', p.name)), reverse=True)
    removed = []
    for folder in folders[keep:]:
        if folder == current:
            continue
        with (folder / '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            shutil.rmtree(folder)
            removed.append(folder.name)
    return removed


class RunSession:
    def __init__(self, root=None, keep=20):
        root = Path(root) if root else Path(__file__).resolve().parent / 'fast_runs'
        root.mkdir(parents=True, exist_ok=True)
        self.folder = root / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.folder.mkdir()
        self.lock = (self.folder / '.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.started = time.perf_counter()
        self.events = []
        self.frames = 0
        self.ocr_calls = 0
        self.finished = False
        prune_runs(root, keep, current=self.folder)

    def flush(self, image=None):
        temporary = self.folder / 'log.json.tmp'
        temporary.write_text(json.dumps(self.events, ensure_ascii=False, indent=2))
        temporary.replace(self.folder / 'log.json')
        if image is not None:
            image.save(self.folder / 'last.jpg', quality=90)

    def close(self):
        self.finished = True
        if not self.lock.closed:
            self.lock.close()
