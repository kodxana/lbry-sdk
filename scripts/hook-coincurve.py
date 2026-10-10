"""Include the backend imported by coincurve's Windows CFFI extension."""
from PyInstaller.compat import is_win

hiddenimports = ['coincurve._cffi_backend'] if is_win else []
