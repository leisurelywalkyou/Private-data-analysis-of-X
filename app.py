"""监控面板入口：pythonw app.py（或用 启动.bat 双击）。

桌宠运行时也会从右键菜单以子进程方式拉起本面板；
可选参数指定初始页，例如 `pythonw app.py monitor`。
"""

import sys

from xmonitor.ui.panel import main

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "overview")
