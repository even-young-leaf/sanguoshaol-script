# 三国杀 OL 免费奖励自动领取

适用于 macOS + Google Chrome 的本地界面自动化脚本，入口为 [4399 三国杀 OL](https://my.4399.com/yxsgs/)。通过界面截图、图片模板、局部文字识别和鼠标操作巡检已适配的免费奖励。

这是按当前电脑和游戏界面校准的版本，尚未实现跨电脑、任意分辨率或 Windows 支持。

## 已适配的流程

- 复用 Chrome 已有的 4399 登录状态，从官网自动进入 OL。
- 每日签到、我要强将体验卡、羽化飞升、日常任务、军典、节钺令。
- 官阶俸禄、公会免费擂鼓、武将免费单抽、活动免费好礼、免费祈福。
- 右下角“更多”中的发财树：仅操作明确免费的按钮。
- 关闭已识别的宣传页及奖励弹窗，并检查关闭结果。
- 切换应用或标签时暂停，切回游戏后继续；暂停时间不计入操作超时。
- 检查浏览器缩放，偏离校准比例时自动恢复到 100%。

红点只是判断依据之一。脚本还检查页面、按钮和免费条件，不执行购买、补签、兑换或消耗已有抽取券的操作。

“全部”指以上已适配入口，不代表能领取所有临时活动。部分新增领取分支仍需在实际可领取状态下验证，详见[新版使用说明](新版使用说明.txt)。

## 安装

建议使用 Python 3.12。先在终端进入下载后的项目目录，再执行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x 启动.command 启动_旧版.command
```

在 macOS“系统设置 → 隐私与安全性”中，允许运行脚本的终端使用辅助功能、屏幕录制，并在系统提示时允许控制 Google Chrome 和 System Events。只给其他应用授权不能代替终端权限。

先在日常使用的 Chrome 用户资料中登录 4399。登录状态失效或出现验证码时，需要在浏览器完成验证；脚本没有保存账号密码，也没有实现无登录状态时自动填写密码。

## 运行

双击 `启动.command`，输入 `1` 或直接回车，一键登录并巡检。

也可以从项目目录执行：

```sh
# 登录并巡检
.venv/bin/python sgs_fast.py --module all --execute

# 只登录并进入大厅
.venv/bin/python sgs_fast.py --module login --execute

# 只读扫描，不点击、不修改缩放
.venv/bin/python sgs_fast.py --module scan

# 保存过程截图以便排查
.venv/bin/python sgs_fast.py --module all --execute --debug
```

运行中可以切换应用，脚本会等待游戏回到前台。它仍使用前台鼠标操作，不能同时在后台领奖。领取期间不要操作游戏；按 `Ctrl+C` 可以结束。

模板按 1657 × 1079 的窗口截图坐标校准。窗口大小、浏览器工具栏或游戏布局不同，可能需要重新校准。自动恢复 100% 缩放不等于已适配任意窗口尺寸；运行中窗口移动或改变大小仍会停止。

## 文件

| 文件 | 用途 |
| --- | --- |
| `sgs_fast.py` | 快速版巡检、页面识别及鼠标操作 |
| `sgs_login.py` | Chrome 标签管理、官网进入及登录就绪检查 |
| `sgs_zoom.py` | 浏览器缩放检查与恢复 |
| `templates_v2.json`、`templates_v2/` | 快速版界面模板及搜索区域 |
| `sgs_daily.py`、`recipes.json`、`templates/` | 第一版实现及其模板，也提供快速版使用的基础能力 |
| `启动_旧版.command`、`使用说明.txt` | 第一版菜单及说明 |

`fast_runs/` 会在本机生成日志和截图。虚拟环境、运行记录、完整校准截图和本机测试日志均不上传。

## 验证

```sh
.venv/bin/python -m py_compile sgs_daily.py sgs_fast.py sgs_login.py sgs_zoom.py
.venv/bin/python verify_focus.py
.venv/bin/python verify_replay.py
.venv/bin/python verify_startup.py
```

`verify_focus.py` 模拟应用及标签切换，不操作实际鼠标。其余两个回放脚本依赖本机历史截图；仓库未包含这些完整截图，缺少时会明确跳过。这些检查不代表已验证全部新活动或所有账号状态。

历史实测：多数奖励已领取时，巡检主体约 8–10 秒；从官网进入游戏还需要加载时间。全部待领取时，弹窗、网络和动画会增加耗时，不能保证几秒内领完。
