#!/bin/zsh
cd "$(dirname "$0")" || exit 1
echo '三国杀 OL 快速版'
echo '自动领取奖励：发财树每天至多150元宝，其余仅处理免费领取。'
echo '切换到其他应用时暂停，切回游戏后自动继续；领取期间请勿操作游戏。'
echo '官网和游戏页的浏览器缩放会自动恢复为 100%。'
echo '如 4399 登录过期，请按提示在浏览器完成登录/验证码，脚本会继续。'
echo '1 一键巡检全部已适配入口（默认）'
echo '2 只巡检任务：体验卡、羽化飞升、日常、军典、节钺令'
echo '3 只领取军典'
echo '4 只领取节钺令'
echo '5 领取发财树（每天至多150元宝）'
echo '6 只读扫描，不点击'
echo '7 打开旧版菜单'
echo '8 只登录并进入大厅'
read 'choice?输入编号，直接回车选1：'
case "${choice:-1}" in
  1) .venv/bin/python sgs_fast.py --module all --execute ;;
  2) .venv/bin/python sgs_fast.py --module tasks --execute ;;
  3) .venv/bin/python sgs_fast.py --module 军典 --execute ;;
  4) .venv/bin/python sgs_fast.py --module 节钺令 --execute ;;
  5) .venv/bin/python sgs_fast.py --module 发财树 --execute ;;
  6) .venv/bin/python sgs_fast.py --module scan ;;
  7) exec ./启动_旧版.command ;;
  8) .venv/bin/python sgs_fast.py --module login --execute ;;
  *) echo '编号无效。' ;;
esac
echo '本次记录在 fast_runs 文件夹。'
read 'finished?按回车关闭窗口。'
