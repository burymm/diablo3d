"""
d1shm_reader.py — чтение состояния TH4 из именованной разделяемой памяти (Р-25)

th43d.exe публикует состояние в "D1BridgeState" через seqlock.
Этот модуль читает его без файлов и без сканирования памяти.

Использование:
    from d1shm_reader import D1ShmReader
    reader = D1ShmReader()
    if reader.open():
        state = reader.read()
        if state:
            print(state['player']['Row'], state['player']['Col'])
        reader.close()
"""

import ctypes
import ctypes.wintypes as wt
import struct
import time

# Константы Win32
FILE_MAP_READ = 0x0004
FILE_MAP_ALL_ACCESS = 0xF001F
PAGE_READWRITE = 0x04
INVALID_HANDLE_VALUE = wt.HANDLE(-1).value

# Имя shared memory
D1BRIDGE_SHM_NAME = "D1BridgeState"
D1BRIDGE_MAGIC = 0x31423144  # 'D1B1'
D1BRIDGE_VERSION = 1

# Размеры
FINE_MAP_SIZE = 112 * 112
TBW_SIZE = 2049
PLAYER_MAP_SIZE = 112 * 112

# Размеры структур
HEADER_SIZE = 24  # 4+4+4+4+8
# Размер структуры игрока публикуется TH4 в header.player_size.
# Поддерживаются две версии: 72 (без CurAction) и 76 (с CurAction).
PLAYER_V1_SIZE = 72
PLAYER_V2_SIZE = 76
COMMAND_SIZE = 28  # 4+4+4+4+4+4+4 = 28 (seq, action, param1-4, timestamp)

# Смещения полей игрока (внутри структуры игрока)
PLAYER_FIELDS_V1 = {
    'Row': 0, 'Col': 2, 'dir': 4, 'dungeon': 6,
    'CurLife': 8, 'MaxCurLife': 12, 'CurMana': 16, 'MaxCurMana': 20,
    'CharLevel': 24, 'ClassID': 26, 'Xp': 28, 'TotalGold': 36, 'name': 40,
}
PLAYER_FIELDS_V2 = {
    'Row': 0, 'Col': 2, 'dir': 4, 'dungeon': 6, 'CurAction': 8,
    'CurLife': 12, 'MaxCurLife': 16, 'CurMana': 20, 'MaxCurMana': 24,
    'CharLevel': 28, 'ClassID': 30, 'Xp': 32, 'TotalGold': 40, 'name': 44,
}

FINE_MAP_BYTES = FINE_MAP_SIZE * 4  # int32
TBW_BYTES = TBW_SIZE               # uint8
PLAYER_MAP_BYTES = PLAYER_MAP_SIZE  # uint8

# Максимальный размер отображения (запас на любую версию раскладки)
MAP_SIZE = (HEADER_SIZE + PLAYER_V2_SIZE + COMMAND_SIZE
            + FINE_MAP_BYTES + TBW_BYTES + PLAYER_MAP_BYTES)

# Смещения полей в shared memory (вычисляются динамически по player_size)
OFF_HEADER = 0
OFF_PLAYER = HEADER_SIZE


class D1ShmReader:
    """Читатель состояния TH4 из разделяемой памяти."""

    def __init__(self):
        self._handle = None
        self._view = None
        self._buf = None
        self._player_size = 0
        self._fields = PLAYER_FIELDS_V1
        self._off_command = 0
        self._off_fine = 0
        self._off_tbw = 0
        self._off_players = 0

    def _recalc_layout(self, player_size):
        """Пересчитать смещения по размеру структуры игрока."""
        if player_size == PLAYER_V2_SIZE:
            self._fields = PLAYER_FIELDS_V2
        else:
            player_size = PLAYER_V1_SIZE
            self._fields = PLAYER_FIELDS_V1
        self._player_size = player_size
        self._off_command = HEADER_SIZE + player_size
        self._off_fine = self._off_command + COMMAND_SIZE
        self._off_tbw = self._off_fine + FINE_MAP_BYTES
        self._off_players = self._off_tbw + TBW_BYTES

    def open(self):
        """Открыть shared memory. Возвращает True при успехе."""
        kernel32 = ctypes.windll.kernel32
        kernel32.GetLastError.restype = wt.DWORD
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]

        # OpenFileMapping
        self._handle = kernel32.OpenFileMappingA(
            FILE_MAP_READ, False, D1BRIDGE_SHM_NAME.encode('ascii')
        )
        if not self._handle:
            err = kernel32.GetLastError()
            print(f"OpenFileMappingA failed: err={err}")
            return False

        # MapViewOfFile — мапим максимум (запас на любую версию)
        self._view = kernel32.MapViewOfFile(
            self._handle, FILE_MAP_READ, 0, 0, MAP_SIZE
        )
        if not self._view:
            err = kernel32.GetLastError()
            print(f"MapViewOfFile failed: err={err}")
            kernel32.CloseHandle(self._handle)
            self._handle = None
            return False

        # Создаём buffer для чтения
        self._buf = ctypes.create_string_buffer(MAP_SIZE)

        # Начальная раскладка (уточним по заголовку при первом чтении)
        self._recalc_layout(PLAYER_V1_SIZE)
        return True

    def close(self):
        """Закрыть shared memory."""
        kernel32 = ctypes.windll.kernel32
        kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        kernel32.UnmapViewOfFile.restype = wt.BOOL
        if self._view:
            kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
        self._buf = None

    def _read_raw(self):
        """Прочитать сырые данные из shared memory."""
        if not self._view or not self._buf:
            return False
        # Используем string_at для копирования из mapped view
        data = ctypes.string_at(self._view, MAP_SIZE)
        ctypes.memmove(self._buf, data, MAP_SIZE)
        return True

    def read(self):
        """
        Прочитать состояние через seqlock.
        Возвращает dict с данными или None при ошибке.
        """
        if not self._buf:
            return None

        max_retries = 10
        for _ in range(max_retries):
            # Первое чтение seq
            if not self._read_raw():
                return None
            seq1 = struct.unpack_from('<I', self._buf, 8)[0]  # offset seq в header

            # Если нечётное — идёт запись, ждём
            if seq1 & 1:
                time.sleep(0.001)
                continue

            # Читаем данные
            # Header
            magic, version, seq, player_size, timestamp_ms = struct.unpack_from(
                '<IIIIQ', self._buf, 0
            )

            if magic != D1BRIDGE_MAGIC:
                return None
            if version != D1BRIDGE_VERSION:
                return None

            # Раскладка могла измениться (новая сборка TH4)
            if player_size != self._player_size:
                self._recalc_layout(player_size)

            # Player — читаем поля по вычисленным смещениям
            player_data = self._parse_player()

            # Второе чтение seq — проверяем, что данные не изменились
            if not self._read_raw():
                return None
            seq2 = struct.unpack_from('<I', self._buf, 8)[0]

            if seq1 != seq2:
                # Данные изменились во время чтения — повторяем
                continue

            # Данные стабильны — возвращаем
            return self._parse_data(timestamp_ms, player_data)

        # Не удалось прочитать за max_retries
        return None

    def _parse_player(self):
        """Прочитать поля игрока по вычисленным смещениям."""
        f = self._fields
        base = HEADER_SIZE

        def i16(key):
            return struct.unpack_from('<h', self._buf, base + f[key])[0]

        def i32(key):
            return struct.unpack_from('<i', self._buf, base + f[key])[0]

        def i64(key):
            return struct.unpack_from('<q', self._buf, base + f[key])[0]

        name_raw = self._buf[base + f['name']: base + f['name'] + 32]

        p = {
            'Row': i16('Row'),
            'Col': i16('Col'),
            'dir': i16('dir'),
            'dungeon': i16('dungeon'),
            'CurLife': i32('CurLife'),
            'MaxCurLife': i32('MaxCurLife'),
            'CurMana': i32('CurMana'),
            'MaxCurMana': i32('MaxCurMana'),
            'CharLevel': i16('CharLevel'),
            'ClassID': i16('ClassID'),
            'Xp': i64('Xp'),
            'TotalGold': i32('TotalGold'),
            'name': name_raw.split(b'\x00')[0].decode('utf-8', errors='replace'),
        }
        if 'CurAction' in f:
            p['CurAction'] = i16('CurAction')
        return p

    def _parse_data(self, timestamp_ms, player_data):
        """Собрать dict с данными."""
        return {
            'timestamp_ms': timestamp_ms,
            'player': player_data,
            'map': {
                'FineMap': self._read_fine_map(),
                'TileBlockWalking': self._read_tbw(),
                'PlayerMap': self._read_player_map(),
            }
        }

    def _read_fine_map(self):
        """Прочитать FineMap[112][112] как список int."""
        data = self._buf[self._off_fine:self._off_fine + FINE_MAP_BYTES]
        return list(struct.unpack(f'<{FINE_MAP_SIZE}i', data))

    def _read_tbw(self):
        """Прочитать TileBlockWalking[2049] как список int."""
        data = self._buf[self._off_tbw:self._off_tbw + TBW_BYTES]
        return list(struct.unpack(f'<{TBW_BYTES}B', data))

    def _read_player_map(self):
        """Прочитать PlayerMap[112][112] как список int."""
        data = self._buf[self._off_players:self._off_players + PLAYER_MAP_BYTES]
        return list(struct.unpack(f'<{PLAYER_MAP_BYTES}b', data))

    def read_simple(self):
        """
        Упрощённое чтение — только герой, без карты.
        Быстро, для watch-цикла.
        """
        result = self.read()
        if not result:
            return None
        return result['player']


def test_reader():
    """Тест чтения из shared memory."""
    reader = D1ShmReader()
    if not reader.open():
        print("Не удалось открыть shared memory 'D1BridgeState'")
        print("Убедитесь, что th43d.exe запущен")
        return

    print(f"Shared memory открыт, размер: {MAP_SIZE} байт")

    for i in range(5):
        state = reader.read()
        if state:
            p = state['player']
            print(f"\n--- Чтение {i+1} ---")
            print(f"  Hero: {p['name']}")
            print(f"  Pos: Row={p['Row']}, Col={p['Col']}")
            print(f"  HP: {p['CurLife']}/{p['MaxCurLife']}")
            print(f"  Mana: {p['CurMana']}/{p['MaxCurMana']}")
            print(f"  Level: {p['CharLevel']}")
            print(f"  Gold: {p['TotalGold']}")
            print(f"  XP: {p['Xp']}")
            print(f"  Dungeon: {p['dungeon']}")
            print(f"  Timestamp: {state['timestamp_ms']} мс")
        else:
            print(f"Чтение {i+1}: failed")
        time.sleep(0.1)

    reader.close()


if __name__ == '__main__':
    test_reader()
