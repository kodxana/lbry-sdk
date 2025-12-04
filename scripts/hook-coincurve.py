"""
Hook for coincurve.
"""

import os
import os.path
import glob
from PyInstaller.utils.hooks import get_module_file_attribute

try:
    coincurve_dir = os.path.dirname(get_module_file_attribute('coincurve'))
    
    # Try to find the secp256k1 library file
    binaries = []
    
    # List of possible library filenames
    possible_files = [
        'libsecp256k1.dll',      # Windows
        'libsecp256k1.so',       # Linux
        'libsecp256k1.so.*',     # Linux with version
        'libsecp256k1.dylib',    # macOS
        '_libsecp256k1.pyd',     # Windows compiled module
        'libsecp256k1-*.dll',    # Windows with version
    ]
    
    # Search in the main directory and common subdirectories
    search_paths = [
        coincurve_dir,
        os.path.join(coincurve_dir, '.libs'),
        os.path.join(coincurve_dir, '_libsecp256k1.libs'),
    ]
    
    for search_path in search_paths:
        if not os.path.exists(search_path):
            continue
        for pattern in possible_files:
            matches = glob.glob(os.path.join(search_path, pattern))
            if matches:
                for match in matches:
                    binaries.append((match, 'coincurve'))
                break
        if binaries:
            break
    
    # If no library files found, it's OK - the library might be statically linked
    # into the Python module itself in newer versions
    
except Exception as e:
    # If there's any error, just set binaries to empty list
    # The module might work without explicit library files
    binaries = []
