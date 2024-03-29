# cbusconfig.py

import gc

from micropython import const

import cbus
# import i2ceeprom
import logger

FILES_CONFIG_FILENAME = const('/config.dat')
FILES_NVS_FILENAME = const('/nvs.dat')
FILES_EVENTS_FILENAME = const('/events.dat')

# JSON_NVS_FILENAME = const('/nvs.json')
# JSON_EVENTS_FILE_NAME = const('/events.json')

CONFIG_TYPE_FILES = const(0)


# CONFIG_TYPE_JSON = const(1)
# CONFIG_TYPE_I2C_EEPROM = const(2)


class storage_backend:
    events = ''
    nvs = ''

    def __init__(self, storage_type=CONFIG_TYPE_FILES, ev_offset: int = 0):
        self.logger = logger.logger()
        self.storage_type = storage_type
        self.ev_offset = ev_offset

    def init_config(self, config):
        pass

    def load_config(self, data_len):
        pass

    def store_config(self, config):
        pass

    def init_events(self, events):
        pass

    def load_events(self, ev_size):
        pass

    def store_events(self, events):
        pass

    def init_nvs(self, nvs):
        pass

    def load_nvs(self, num_nvs):
        pass

    def store_nvs(self, nvs):
        pass


# backend using binary files

class files_backend(storage_backend):
    def __init__(self, ev_offset: int = 0):
        self.logger = logger.logger()
        super().__init__(ev_offset)

    def init_config(self, config):
        f = open(FILES_CONFIG_FILENAME, 'wb')
        f.write(bytearray(config))
        f.close()

    def load_config(self, data_len):
        try:
            f = open(FILES_CONFIG_FILENAME, 'rb')
        except OSError:
            return None

        try:
            data = f.read()
        except UnicodeError:
            return None

        f.close()
        return bytearray(data)

    def store_config(self, config):
        f = open(FILES_CONFIG_FILENAME, 'wb')
        f.write(bytearray(config))
        f.close()

    def init_events(self, events):
        f = open(FILES_EVENTS_FILENAME, 'wb')
        f.write(bytearray(events))
        f.close()

    def load_events(self, ev_size):
        try:
            f = open(FILES_EVENTS_FILENAME, 'rb')
        except OSError:
            return None

        try:
            data = f.read()
        except UnicodeError:
            return None

        f.close()
        return bytearray(data)

    def store_events(self, events):
        f = open(FILES_EVENTS_FILENAME, 'wb')
        f.write(bytearray(events))
        f.close()

    def init_nvs(self, nvs):
        f = open(FILES_NVS_FILENAME, 'wb')
        f.write(bytearray(nvs))
        f.close()

    def load_nvs(self, num_nvs):
        try:
            f = open(FILES_NVS_FILENAME, 'rb')
        except OSError:
            return None

        try:
            data = f.read()
        except UnicodeError:
            return None

        f.close()
        return bytearray(data)

    def store_nvs(self, nvs):
        f = open(FILES_NVS_FILENAME, 'wb')
        f.write(bytearray(nvs))
        f.close()


# backend using json text files

# class json_backend(storage_backend):
#
#     def __init__(self, ev_offset: int = 0):
#         self.logger = logger.logger()
#         super(json_backend, self).__init__(ev_offset)
#
#     @staticmethod
#     def dict_from_array(a: list) -> dict:
#         d = dict([(key, value) for key, value in enumerate(a)])
#         return d
#
#     def init_events(self, events):
#         f = open(JSON_EVENTS_FILE_NAME, 'w')
#         d = self.dict_from_array(events)
#         s = json.dumps(d)
#         f.write(bytearray(s))
#         f.close()
#
#     def load_events(self, ev_size):
#         try:
#             f = open(JSON_EVENTS_FILE_NAME, 'r')
#         except OSError:
#             return None
#
#         try:
#             data = f.read()
#         except UnicodeError:
#             return None
#
#         f.close()
#         s = data.encode('ascii')
#         d = json.loads(s)
#         b = bytearray(d.values())
#         return bytearray(b)
#
#     def store_events(self, events):
#         f = open(JSON_EVENTS_FILE_NAME, 'w')
#         d = self.dict_from_array(events)
#         s = json.dumps(d)
#         f.write(bytearray(s))
#         f.close()
#
#     def init_nvs(self, nvs):
#         with open(JSON_NVS_FILENAME, 'w') as f:
#             d = self.dict_from_array(nvs)
#             s = json.dumps(d)
#             f.write(bytearray(s))
#
#     def load_nvs(self, num_nvs):
#         try:
#             f = open(JSON_NVS_FILENAME, 'r')
#         except OSError:
#             return None
#
#         try:
#             data = f.read()
#         except UnicodeError:
#             return None
#
#         f.close()
#         s = data.encode('ascii')
#         d = json.loads(s)
#         b = bytearray(d.values())
#         return bytearray(b)
#
#     def store_nvs(self, nvs):
#         f = open(JSON_NVS_FILENAME, 'w')
#         d = self.dict_from_array(nvs)
#         s = json.dumps(d)
#         f.write(bytearray(s))
#         f.close()


# class eeprom_backend(storage_backend):
#     def __init__(self, ev_offset):
#         self.logger = logger.logger()
#         # self.logger.log(f'eeprom_backend init, offset = {ev_offset}')
#         super().__init__(ev_offset)
#         self.eeprom = i2ceeprom.i2ceeprom()
#
#     def load_events(self, ev_size):
#
#         data = bytearray()
#
#         for i in range(0, ev_size):
#             data.extend(self.eeprom.read(i + self.ev_offset))
#
#         return data
#
#     def store_events(self, events):
#         for i in range(0, len(events)):
#             self.eeprom.write((i + self.ev_offset), events[i])
#
#     def load_nvs(self, num_nvs):
#
#         data = bytearray()
#
#         for i in range(0, num_nvs):
#             data.extend(self.eeprom.read(i))
#
#         return data
#
#     def store_nvs(self, nvs):
#         for i in range(0, len(nvs)):
#             self.eeprom.write(i, nvs[i])


class cbusconfig:
    def __init__(self, storage_type=CONFIG_TYPE_FILES, num_nvs=20, num_events=64, num_evs=4):
        self.logger = logger.logger()
        self.storage_type = storage_type

        self.num_nvs = num_nvs
        self.num_events = num_events
        self.num_evs = num_evs
        self.event_size = 4 + self.num_evs

        if self.storage_type == CONFIG_TYPE_FILES:
            self.backend = files_backend()
        # elif self.storage_type == CONFIG_TYPE_JSON:
        #     self.backend = json_backend()
        else:
            raise ValueError('unknown storage type')

        self.mode = 0
        self.canid = 0
        self.node_number = 0
        self.was_reset = False

    def begin(self) -> None:
        # load or init module config data
        self.config_data = self.backend.load_config(10)

        if not self.config_data:
            self.config_data = bytearray(0x0 for _ in range(10))
            self.backend.init_config(self.config_data)

        self.mode = self.config_data[0]
        self.canid = self.config_data[1]
        self.node_number = (self.config_data[2] << 8) + self.config_data[3]
        self.was_reset = self.config_data[4]

        # load or init NVs
        self.nvs = self.backend.load_nvs(self.num_nvs)

        if not self.nvs:
            self.nvs = bytearray(0x0 for _ in range(self.num_nvs))
            self.backend.init_nvs(self.nvs)

        # load or init events
        self.events = self.backend.load_events(self.num_events * self.event_size)

        if not self.events:
            self.events = bytearray(0xff for _ in range(self.num_events * self.event_size))
            self.backend.init_events(self.events)

    def set_mode(self, mode: int) -> None:
        self.config_data[0] = mode
        self.backend.store_config(self.config_data)
        self.mode = mode

    def set_canid(self, canid: int) -> None:
        self.config_data[1] = canid
        self.backend.store_config(self.config_data)
        self.canid = canid

    def set_node_number(self, node_number: int) -> None:
        self.config_data[2] = int(node_number >> 8)
        self.config_data[3] = node_number & 0xff
        self.backend.store_config(self.config_data)
        self.node_number = node_number

    def set_reset_flag(self, state: bool) -> None:
        self.config_data[4] = state
        self.backend.store_config(self.config_data)

    def find_existing_event(self, nn: int, en: int, opcode: int=0) -> int:
        if opcode & (1 << 3):
            # zero the NN for short events
            nn = 0

        for i in range(self.num_events):
            offset = i * self.event_size

            if ((self.events[offset] << 8) + self.events[offset + 1]) == nn and (
                    (self.events[offset + 2] << 8) + self.events[offset + 3]) == en:
                return i

        return -1

    def find_event_by_ev(self, evnum: int, evval: int) -> int:
        for i in range(self.num_events):
            if self.read_event_ev(i, evnum) == evval:
                return i
        return -1

    # test ... mod.cbus.config.find_event_by_evs(((1, 3), (2, 6), (3, 9), (4, 12),))

    def find_event_by_evs(self, query: tuple[tuple[int, int], ...]) -> int:
        for i in range(self.num_events):
            found = True
            for j in range(len(query)):
                if self.read_event_ev(i, query[j][0]) != query[j][1]:
                    found = False
                    break
            if found:
                return i
        return -1

    def find_event_space(self) -> int:
        for i in range(self.num_events):
            offset = i * self.event_size

            if (
                    self.events[offset] == 0xff
                    and self.events[offset + 1] == 0xff
                    and self.events[offset + 2] == 0xff
                    and self.events[offset + 3] == 0xff
            ):
                return i

        return -1

    def read_event(self, index: int) -> bytearray:
        offset = self.event_size * index
        return self.events[offset: offset + self.event_size]

    def write_event(self, nn: int, en: int, evnum: int, evval: int) -> bool:
        idx = self.find_existing_event(nn, en)

        if idx < 0:
            idx = self.find_event_space()
            if idx < 0:
                return False

        offset = idx * self.event_size
        self.events[offset] = int(nn >> 8)
        self.events[offset + 1] = nn & 0xff
        self.events[offset + 2] = int(en >> 8)
        self.events[offset + 3] = en & 0xff
        self.events[offset + 4 + (evnum - 1)] = evval

        self.backend.store_events(self.events)
        return True

    def read_event_ev(self, idx: int, evnum: int) -> int:
        return self.events[(idx * self.event_size) + 4 + (evnum - 1)]

    def write_event_ev(self, idx, evnum: int, evval: int) -> None:
        self.events[(idx * self.event_size) + 4 + (evnum - 1)] = evval
        self.backend.store_events(self.events)

    def clear_event(self, nn: int, en: int) -> bool:
        idx = self.find_existing_event(nn, en)

        if idx < 0:
            return False

        for i in range(self.event_size):
            self.events[(idx * self.event_size) + 1] = 0xff

        self.backend.store_events(self.events)
        return True

    def count_events(self) -> int:
        count = 0

        for i in range(self.num_events):
            t = self.read_event(i)
            if t[0] == 0xff and t[1] == 0xff and t[2] == 0xff and t[3] == 0xff:
                pass
            else:
                count += 1

        return count

    def clear_all_events(self) -> None:
        self.events = bytearray([0xff] * (self.num_events * self.event_size))
        self.backend.store_events(self.events)

    def read_nv(self, nvnum: int) -> int:
        return self.nvs[nvnum - 1]

    def write_nv(self, nvnum: int, value: int) -> None:
        self.nvs[nvnum - 1] = value
        self.backend.store_nvs(self.nvs)

    def print_event_table(self, hex: bool = True, print_all: bool = False) -> None:
        for i in range(self.num_events):
            if print_all or (self.events[i * self.event_size] < 0xff):
                print(f'{i:3} = ', end='')
                for j in range(0, self.event_size):
                    if hex:
                        print(f'{self.events[(i * self.event_size) + j]:02x} ', end='')
                    else:
                        print(f'{self.events[(i * self.event_size) + j]:03} ', end='')
                print()

    def print_nvs(self) -> None:
        for i, nv in enumerate(self.nvs):
            print(f'{i + 1:3} = {nv:03} 0x{nv:02x}')

    def print_config(self) -> None:
        for i, cf in enumerate(self.config_data):
            print(f'{i:3} = {cf:03} 0x{cf:02x}')

    def reset_module(self) -> None:
        if self.mode == cbus.MODE_SLIM:
            self.logger.log('reset_module')
            self.config_data = bytearray(0x0 for _ in range(10))
            self.nvs = bytearray(0x0 for _ in range(self.num_nvs))
            self.events = bytearray(0xff for _ in range(self.num_events * self.event_size))
            self.backend.store_config(self.config_data)
            self.backend.store_nvs(self.nvs)
            self.backend.store_events(self.events)
            self.set_reset_flag(True)
            self.reboot()
        else:
            self.logger.log('set module to SLiM before resetting')

    @staticmethod
    def reboot() -> None:
        import machine
        machine.soft_reset()

    @staticmethod
    def free_memory() -> int:
        gc.collect()
        return gc.mem_free()
