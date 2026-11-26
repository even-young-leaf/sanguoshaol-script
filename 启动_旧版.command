#!/bin/zsh
cd "$(dirname "$0")" || exit 1
echo '三国杀 OL 免费领取原型（Mac / Chrome）'
echo '先手动打开对应游戏页面，再在此选择。脚本会把 Chrome 切到前台。'
echo '1 只扫描（不点击）'
echo '2 福利 → 每日签到'
echo '3 任务 → 左侧的“任务”标签（日常任务）'
echo '4 官阶 → 每日俸禄'
echo '5 公会 → 公会擂鼓（仅常山战鼓免费次数）'
echo '6 武将 → 招武将 → 常驻招募'
echo '7 祈福 → 小雪祈福'
echo '8 活动 → 充消返利 → 充值福利 → 免费好礼'
read 'choice?输入编号：'
case "$choice" in
  1) .venv/bin/python sgs_daily.py scan --delay 2 ;;
  2) .venv/bin/python sgs_daily.py run --module 签到 --execute --focus --delay 2 ;;
  3) .venv/bin/python sgs_daily.py run --module 任务 --execute --focus --delay 2 ;;
  4) .venv/bin/python sgs_daily.py run --module 官阶 --execute --focus --delay 2 ;;
  5) .venv/bin/python sgs_daily.py run --module 公会擂鼓 --execute --focus --delay 2 ;;
  6) .venv/bin/python sgs_daily.py run --module 武将抽取 --execute --focus --delay 2 ;;
  7) .venv/bin/python sgs_daily.py run --module 祈福 --execute --focus --delay 2 ;;
  8) .venv/bin/python sgs_daily.py run --module 活动 --execute --focus --delay 2 ;;
  *) echo '未选择有效编号。' ;;
esac
echo '本次结束。记录保存在 runs 文件夹。'
read 'finished?按回车关闭此窗口。'
