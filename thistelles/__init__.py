try:
    from importlib.metadata import version as _v
    __version__ = _v("thistelles")
except Exception:
    __version__ = "0.1.0"
