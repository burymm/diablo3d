"""Диагностика доступа к shared memory D1BridgeState"""
import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32
kernel32.GetLastError.restype = wintypes.DWORD

names = [
    b'D1BridgeState',
    b'Global\\D1BridgeState',
    b'Local\\D1BridgeState',
]

access_modes = [
    (0x0004, 'FILE_MAP_READ'),
    (0xF001F, 'FILE_MAP_ALL_ACCESS'),
    (0x0002, 'FILE_MAP_WRITE'),
]

print("=== D1BridgeState Shared Memory Diagnostic ===")
print()

for name in names:
    for access, mode_name in access_modes:
        h = kernel32.OpenFileMappingA(access, False, name)
        err = kernel32.GetLastError()
        if h:
            print(f'OK: "{name.decode()}" {mode_name} (handle={h})')
            kernel32.CloseHandle(h)
        else:
            print(f'FAIL: "{name.decode()}" {mode_name} (err={err})')
    print()

# Также проверим, запущен ли th43d.exe
import subprocess
result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq th43d.exe'], capture_output=True, text=True)
if 'th43d' in result.stdout:
    print("th43d.exe is RUNNING")
else:
    print("th43d.exe is NOT running")
