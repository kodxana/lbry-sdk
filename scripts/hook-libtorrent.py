"""
Hook for libtorrent on Windows.

The original hook assumed OpenSSL 1.1 DLLs were present in System32.
Modern libtorrent wheels may ship OpenSSL 3.x DLLs alongside the .pyd, and
Windows hosts often lack the 1.1 DLLs entirely. This hook now:
  1) Looks for libssl*/libcrypto* in the libtorrent package directory.
  2) Falls back to common System32 names for OpenSSL 3.x and 1.1.
  3) Always bundles the libtorrent .pyd(s).
"""

import glob
import os
import os.path
from PyInstaller import compat
from PyInstaller.utils.hooks import get_module_file_attribute


def _maybe_add(patterns, dest, acc):
    for pattern in patterns:
        for path in glob.glob(pattern):
            if os.path.isfile(path):
                acc.append((path, dest))


def get_binaries():
    bins = []
    if not compat.is_win:
        return bins

    # 1) Prefer DLLs colocated with the libtorrent extension
    lt_file = get_module_file_attribute('libtorrent')
    lt_dir = os.path.dirname(lt_file)
    _maybe_add(
        [
            os.path.join(lt_dir, 'libssl*-x64.dll'),
            os.path.join(lt_dir, 'libcrypto*-x64.dll'),
        ],
        '.',
        bins,
    )

    # 2) Fall back to common install locations (System32 and OpenSSL-Win64 bin)
    sys32 = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'System32')
    openssl_bin = os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'OpenSSL-Win64', 'bin')
    fallbacks = [
        os.path.join(sys32, 'libssl-3-x64.dll'),
        os.path.join(sys32, 'libcrypto-3-x64.dll'),
        os.path.join(sys32, 'libssl-1_1-x64.dll'),
        os.path.join(sys32, 'libcrypto-1_1-x64.dll'),
        os.path.join(openssl_bin, 'libssl-3-x64.dll'),
        os.path.join(openssl_bin, 'libcrypto-3-x64.dll'),
        os.path.join(openssl_bin, 'libssl-1_1-x64.dll'),
        os.path.join(openssl_bin, 'libcrypto-1_1-x64.dll'),
    ]
    for path in fallbacks:
        if os.path.isfile(path) and not any(os.path.basename(path) == os.path.basename(b[0]) for b in bins):
            bins.append((path, '.'))

    # 3) Always include libtorrent extension modules
    for file in glob.glob(os.path.join(lt_dir, 'libtorrent*pyd*')):
        bins.append((file, 'libtorrent'))
    return bins


binaries = get_binaries()
