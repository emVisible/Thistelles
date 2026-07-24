import sys

if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
    try:
        from importlib.metadata import version
        print(f"thistelles {version('thistelles')}")
    except Exception:
        print("thistelles")
    sys.exit(0)

from .main import main

main()
