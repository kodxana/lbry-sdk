"""
Hook for libtorrent.
"""

import os
import sys
from PyInstaller import compat


def get_binaries():
    if compat.is_win:
        # The managed Python 3.9 runtime supplies the DLLs required by the
        # libtorrent 2.0.6 wheel. Do not depend on a system OpenSSL installation.
        files = ('libssl-1_1-x64.dll', 'libcrypto-1_1-x64.dll')
        return [(os.path.join(sys.base_prefix, 'DLLs', file), '.') for file in files]
    return []


binaries = get_binaries()
