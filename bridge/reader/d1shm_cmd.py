"""
d1shm_cmd.py — запись команд GMod → shared memory → TH4 (destAction)

Использование:
    from d1shm_cmd import D1ShmCommand
    cmd = D1ShmCommand()
    if cmd.open():
        cmd.send_walk(1)      # WALKUR
        cmd.send_attack(20, 5)  # MELEE_ATTACK to monster 5
        cmd.close()
"""
import ctypes
import ctypes.wintypes as wt
import time

FILE_MAP_ALL_ACCESS = 0xF001F
D1BRIDGE_SHM_NAME = "D1BridgeState"

# Размеры (должны совпадать с C++)
FINE_MAP_SIZE = 112 * 112
TBW_SIZE = 2049
PLAYER_MAP_SIZE = 112 * 112
HEADER_SIZE = 24
PLAYER_V1_SIZE = 72
PLAYER_V2_SIZE = 76
COMMAND_SIZE = 28  # 4+4+4+4+4+4+4 = 28 (seq, action, param1-4, timestamp)

OFF_HEADER = 0
OFF_PLAYER = HEADER_SIZE
# Максимальный размер отображения
MAP_SIZE = (OFF_PLAYER + PLAYER_V2_SIZE + COMMAND_SIZE
            + FINE_MAP_SIZE * 4 + TBW_SIZE + PLAYER_MAP_SIZE)


class D1ShmCommand:
    """Запись команд в shared memory для TH4."""

    def __init__(self):
        self._handle = None
        self._view = None
        self._seq = 0
        self._off_command = OFF_PLAYER + PLAYER_V1_SIZE

    def _detect_layout(self):
        """Определить смещение команды по header.player_size."""
        try:
            data = ctypes.string_at(self._view, 16)
            player_size = struct.unpack_from('<I', data, 12)[0]
        except Exception:
            player_size = 0
        if player_size not in (PLAYER_V1_SIZE, PLAYER_V2_SIZE):
            player_size = PLAYER_V1_SIZE
        self._off_command = OFF_PLAYER + player_size

    def open(self):
        """Открыть shared memory для записи."""
        kernel32 = ctypes.windll.kernel32
        kernel32.GetLastError.restype = wt.DWORD
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]

        self._handle = kernel32.OpenFileMappingA(
            FILE_MAP_ALL_ACCESS, False, D1BRIDGE_SHM_NAME.encode('ascii')
        )
        if not self._handle:
            return False

        self._view = kernel32.MapViewOfFile(
            self._handle, FILE_MAP_ALL_ACCESS, 0, 0, MAP_SIZE
        )
        if not self._view:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            return False

        return True

    def close(self):
        """Закрыть shared memory."""
        kernel32 = ctypes.windll.kernel32
        kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        if self._view:
            kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def _write_command(self, action, param1=0, param2=0, param3=0, param4=0):
        """Записать команду в shared memory."""
        if not self._view:
            return False

        self._seq += 1
        # GetTickCount-подобный таймер: младшие 32 бита миллисекунд
        timestamp = int(time.monotonic() * 1000) & 0xFFFFFFFF

        # Пишем структуру D1BridgeCommand
        data = struct.pack('<IIiiiiI',
            self._seq & 0xFFFFFFFF, action, param1, param2, param3, param4, timestamp)
        assert len(data) == 28, f"Expected 28 bytes, got {len(data)}"

        # Смещение команды зависит от раскладки игрока — определяем каждый раз
        self._detect_layout()
        ctypes.memmove(self._view + self._off_command, data, COMMAND_SIZE)
        return True

    # Команды движения (PCMD_1..8 = WALKUR..WALKL)
    def send_walk(self, direction):
        """
        Отправить команду движения.
        direction: 1=WALKUR, 2=WALKUL, 3=WALKDR, 4=WALKDL,
                   5=WALKU, 6=WALKR, 7=WALKD, 8=WALKL
        """
        return self._write_command(direction)

    # Команды атаки
    def send_melee_attack(self, monster_index):
        """Атака ближнего боя по монстру."""
        return self._write_command(20, monster_index)

    def send_range_attack(self, monster_index):
        """Атака дальнего боя по монстру."""
        return self._write_command(22, monster_index)

    def send_cast_spell(self, monster_index, spell_level=0):
        """Каст заклинания по монстру."""
        return self._write_command(24, monster_index, spell_level)

    def send_cast_spell_no_orient(self, spell_id):
        """Каст заклинания без ориентации."""
        return self._write_command(26, spell_id)

    def send_stand(self):
        """Остановиться."""
        return self._write_command(0)


import struct
