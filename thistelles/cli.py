import sys

try:
    from importlib.metadata import version as _version
    _VER = _version("thistelles")
except Exception:
    _VER = "?"


def entry():
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        print(f"thistelles {_VER}")
        return
    from .main import main

    main()
