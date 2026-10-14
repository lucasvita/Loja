"""Entry point used by PyInstaller (absolute imports for frozen execution)."""
from hilf_print.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
