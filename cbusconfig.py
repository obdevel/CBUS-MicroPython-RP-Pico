# cbusconfig.py

import gc

from micropython import const

# import i2ceeprom
import logger

nvs_file_name = const('/nvs.dat')
events_file_name = const('/events.dat')

CONFIG_TYPE_FILES = const(0)
CONFIG_TYPE_I2C_EEPROM = const(1)


class storage_backend:
    events = ''
    nvs = ''

    def __init__(self, storage_type=CONFIG_TYPE_FILES, ev_offset=0):
        self.logger = logger.logger()
        self.storage_type = storage_type
        self.ev_offset = ev_offset

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

    def __str__(self):
        pass


class files_backend(storage_backend):
    def __init__(self, ev_offset):
        self.logger = logger.logger()
        super().__init__(ev_offset)

    def init_events(self, events):
        f = open(events_file_name, 'w')
        f.write(bytearray(events))
        f.close()

    def load_events(self, ev_size):
        try:
            f = open(events_file_name, 'r')
        except OSError:
            self.logger.log('file does not exist')
            return None

        data = f.read()
        f.close()
        return bytearray(data.encode('ascii'))

    def store_events(self, events):
        f = open(events_file_name, 'w')
        f.write(bytearray(events))
        f.close()

    def init_nvs(self, nvs):
        f = open(nvs_file_name, 'w')
        f.write(bytearray(nvs))
        f.close()

    def load_nvs(self, num_nvs):
        try:
            f = open(nvs_file_name, 'r')
        except OSError:
            self.logger.log('file does not exist')
            return None

        data = f.read()
        f.close()
        return bytearray(data.encode('ascii'))

    def store_nvs(self, nvs):
        f = open(nvs_file_name, 'w')
        f.write(bytearray(nvs))
        f.close()


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
        self.event_size = self.num_evs + 4

        self.events = bytearray(self.num_events * self.event_size)
        self.nvs = bytearray(10 + self.num_nvs)

        if self.storage_type == CONFIG_TYPE_FILES:
            self.backend = files_backend(0)
        # elif self.storage_type == CONFIG_TYPE_I2C_EEPROM:
        #     self.backend = eeprom_backend(self.num_evs)
        else:
            raise TypeError('unknown storage type')

        self.mode = 0
        self.canid = 0
        self.node_number = 0
        self.was_reset = False

    def begin(self) -> None:
        data = self.backend.load_events(len(self.events))

        if data is None:
            self.backend.init_events(self.events)
            data = self.backend.load_events(self.num_events)

        self.events = data
        data = self.backend.load_nvs(self.num_nvs + 10)

        if data is None:
            self.backend.init_nvs(self.nvs)
            data = self.backend.load_nvs(self.num_nvs + 10)

        self.nvs = data
        self.load_module_info()
        self.was_reset = self.nvs[4]

    def set_mode(self, mode: int) -> None:
        self.nvs[0] = mode
        self.backend.store_nvs(self.nvs)
        self.mode = mode

    def set_canid(self, canid: int) -> None:
        self.nvs[1] = canid
        self.backend.store_nvs(self.nvs)
        self.canid = canid

    def set_node_number(self, node_number: int) -> None:
        self.nvs[2] = int(node_number << 8)
        self.nvs[3] = node_number & 0xff
        self.backend.store_nvs(self.nvs)
        self.node_number = node_number

    def find_existing_event(self, nn: int, en: int) -> int:
        for i in range(self.num_events):
            offset = i * self.event_size

            if ((self.events[offset] >> 8) + self.events[offset + 1]) == nn and (
                    (self.events[offset + 2] >> 8) + self.events[offset + 3]
            ) == en:
                return i

        return -1

    def find_event_by_ev(self, evnum: int, evval: int) -> int:
        for i in range(self.num_events):
            if self.read_event_ev(i, evnum) == evval:
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
        data = bytearray(self.event_size)
        offset = self.event_size * index

        for i in range(self.event_size):
            data[i] = self.events[offset + i]

        return data

    def write_event(self, nn: int, en: int, evnum: int, evval: int) -> bool:
        idx = self.find_existing_event(nn, en)

        if idx < 0:
            # self.logger.log('event not found')
            idx = self.find_event_space()
            if idx < 0:
                # self.logger.log('no free event space')
                return False

        offset = idx * self.event_size
        self.events[offset] = int(nn >> 8)
        self.events[offset + 1] = nn & 0xff
        self.events[offset + 2] = int(en >> 8)
        self.events[offset + 3] = en & 0xff
        self.events[offset + 4 + (evnum - 1)] = evval

        self.backend.store_events(self.events)
        # self.logger.log('wrote event ok')
        return True

    def read_event_ev(self, idx: int, evnum: int) -> int:
        offset = (idx * self.event_size) + 4 + (evnum - 1)
        return self.events[offset]

    def write_event_ev(self, idx, evnum: int, evval: int) -> None:
        offset = (idx * self.event_size) + 4 + (evnum - 1)
        self.events[offset] = evval
        self.backend.store_events(self.events)

    def clear_event(self, nn: int, en: int) -> bool:
        idx = self.find_existing_event(nn, en)

        if not idx:
            return False

        for i in range(self.event_size):
            self.events[i + (idx * self.event_size)] = 0xff

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
        # self.events = bytearray(0xff) * ((self.num_evs + 4) * self.num_events)
        for x in range((self.num_evs + 4) * self.num_events):
            self.events[x] = 0xff
        self.backend.store_events(self.events)

    def read_nv(self, nvnum: int) -> int:
        return self.nvs[nvnum + 9]

    def write_nv(self, nvnum, value):
        self.nvs[nvnum + 9] = value
        self.backend.store_nvs(self.nvs)

    def load_module_info(self) -> None:
        self.mode = self.nvs[0]
        self.canid = self.nvs[1]
        self.node_number = (self.nvs[2] << 8) + self.nvs[3]

    def print_events(self, print_all: bool = False) -> None:
        for i in range(self.num_events):
            if print_all or (self.events[i * self.event_size] < 0xff):
                print(f'{i:02x} = ', end='')
                for j in range(0, self.event_size):
                    print(f'{self.events[(i * self.event_size) + j]:02x} ', end='')
                print()

    def print_nvs(self) -> None:
        for i in range(self.num_nvs + 10):
            print(f'{i:2} - {self.nvs[i]}')

    def reboot(self) -> None:
        import machine
        machine.soft_reset()

    def reset_module(self) -> None:
        self.logger.log('reset_module')
        self.nvs = bytearray(10 + self.num_nvs)
        self.events = bytearray((self.num_evs + 4) * self.num_events)
        self.backend.store_events(self.events)
        self.backend.store_nvs(self.nvs)
        self.set_reset_flag(True)
        self.reboot()

    def set_reset_flag(self, set: bool) -> None:
        self.nvs[4] = set
        self.backend.store_nvs(self.nvs)

    def free_memory(self) -> int:
        gc.collect()
        return gc.mem_free()
