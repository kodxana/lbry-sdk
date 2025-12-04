# Change Log

## [0.115.0] - 2024-11-21

### 🚀 Major Release: Python 3.14 Modernization

This release brings full Python 3.14 compatibility and modernizes the entire asyncio codebase.

### ✨ Highlights
- **Python 3.14 Support**: Complete modernization for Python 3.14 compatibility
- **Asyncio Modernization**: All deprecated patterns updated to modern Python standards

### 🔧 Fixed
- Critical RPC server issue (#2769) that blocked Python 3.8+ compatibility
- Event loop management across 40+ files
- PyInstaller multiprocessing support
- Protobuf compatibility issues in binaries
- UPnP and LAN discovery event loop issues

### 📦 Dependencies
- Python requirement: >=3.14
- Updated all major dependencies for Python 3.14
