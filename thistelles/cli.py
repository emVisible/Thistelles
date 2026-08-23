import os
import subprocess
import sys

try:
    from importlib.metadata import version as _version
    _VER = _version("thistelles")
except Exception:
    _VER = "?"

APP_BUNDLE = "/Applications/Thistelles.app"


def _forward_to_bundle() -> bool:
    """CLI 裸 python 无 bundle 身份：系统弹窗（TCC 授权/通知）会显示
    「Python3」+空白图标。已安装 .app 时转发给 bundle 启动，
    让进程获得 Thistelles 身份；THISTELLES_FORCE_CLI=1 可跳过（开发用）。
    """
    if os.environ.get("THISTELLES_FORCE_CLI") == "1":
        return False
    try:
        from Foundation import NSBundle

        if NSBundle.mainBundle().bundleIdentifier():
            return False  # 已有 bundle 身份（从 .app 启动）
    except Exception:
        pass
    if not os.path.isdir(APP_BUNDLE):
        return False
    subprocess.Popen(["open", APP_BUNDLE])
    print("thistelles: launched from /Applications/Thistelles.app "
          "(CLI 运行无应用身份；如需 CLI 调试请设 THISTELLES_FORCE_CLI=1)")
    return True


def entry():
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        print(f"thistelles {_VER}")
        return
    if _forward_to_bundle():
        return
    from .main import main

    main()
