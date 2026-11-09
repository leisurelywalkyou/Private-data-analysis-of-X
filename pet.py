"""桌宠主程序入口：pythonw pet.py（或用 启动.bat 双击）。

python pet.py --selftest 运行无交互自检；打包后 --panel [页面] 启动观测台。
"""

import sys

from xmonitor.ui.pet import main, selftest


def panel_page(args: list[str]) -> str | None:
    if "--panel" in args:
        i = args.index("--panel")
        return args[i + 1] if len(args) > i + 1 else "overview"
    return None


if __name__ == "__main__":
    page = panel_page(sys.argv[1:])
    if page is not None:
        from xmonitor.ui.panel import main as panel_main

        raise SystemExit(panel_main(page))
    raise SystemExit(selftest() if "--selftest" in sys.argv else main())
