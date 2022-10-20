# cbusconfig.py

import gc
import machine
import i2ceeprom

nvs_file_name = "/nvs.dat"
events_file_name = "/events.dat"

CONFIG_TYPE_FILES = 0
CONFIG_TYPE_I2C_EEPROM = 1


class storage_backend:

    """abstract base class for event and config storage. Other concrete classes must derive from this class"""

    events = ""
    nvs = ""

    def __init__(self, storage_type=CONFIG_TYPE_FILES, ev_offset=0):
        print(
            f"** storage_backend constructor, type = {storage_type}, offset = {ev_offset}"
        )
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
        print("** files_backend init")
        super().__init__(self, ev_offset)

    def init_events(self, events):
        print("** files_backend init_events")

        f = open(events_file_name, "w")
        f.write(bytearray(events))
        f.close()

    def load_events(self, ev_size):
        print("** files_backend load_events")

        try:
            f = open(events_file_name, "r")
        except OSError:
            print("file does not exist")
            return None

        data = f.read()
        f.close()
        return bytearray(data.encode("ascii"))

    def store_events(self, events):
        print("** files_backend store_events")

        f = open(events_file_name, "w")
        f.write(bytearray(events))
        f.close()

    def init_nvs(self, nvs):
        print("** files_backend init_nvs")

        f = open(nvs_file_name, "w")
        f.write(bytearray(nvs))
        f.close()

    def load_nvs(self, num_nvs):
        print("** files_backend load_nvs")

        try:
            f = open(nvs_file_name, "r")
        except OSError:
            print("file does not exist")
            return None

        data = f.read()
        f.close()
        return bytearray(data.encode("ascii"))

    def store_nvs(self, nvs):
        print("** files_backend store_nvs")

        f = open(nvs_file_name, "w")
        f.write(bytearray(nvs))
        f.close()


class eeprom_backend(storage_backend):
    def __init__(self, ev_offset):
        print(f"** eeprom_backend init, offset = {ev_offset}")
        super().__init__(self, ev_offset)
        self.eeprom = i2ceeprom.i2ceeprom()

    def load_events(self, ev_size):

        data = bytearray()

        for i in range(0, ev_size):
            data.extend(self.eeprom.read(i + self.ev_offset))

        return data

    def store_events(self, events):
        for i in range(0, len(events)):
            self.eeprom.write((i + self.ev_offset), events[i])

    def load_nvs(self, num_nvs):

        data = bytearray()

        for i in range(0, num_nvs):
            data.extend(self.eeprom.read(i))

        return data

    def store_nvs(self, nvs):
        for i in range(0, len(nvs)):
            self.eeprom.write(i, nvs[i])


class cbusconfig:
    def __init__(
        self, storage_type=CONFIG_TYPE_FILES, num_nvs=20, num_events=64, num_evs=4
    ):
        print(f"** cbusconfig constructor, storage type = {storage_type}")

        self.storage_type = storage_type

        self.num_nvs = num_nvs
        self.num_events = num_events
        self.num_evs = num_evs
        self.event_size = self.num_evs + 4

        self.events = bytearray(self.num_events * self.event_size)
        self.nvs = bytearray(10 + self.num_nvs)

        if self.storage_type == CONFIG_TYPE_FILES:
            self.backend = files_backend(0)
        elif self.storage_type == CONFIG_TYPE_I2C_EEPROM:
            self.backend = eeprom_backend(self.num_evs)
        else:
            raise TypeError("unknown storage type")

        self.mode = 0
        self.canid = 0
        self.node_number = 0

    def begin(
        self,
    ):
        print("** cbusconfig begin")

        data = self.backend.load_events(len(self.events))

        if data is None:
            self.backend.init_events(self.events)
            data = self.backend.load_events()

        self.events = data

        data = self.backend.load_nvs(self.num_nvs + 10)

        if data is None:
            self.backend.init_nvs(self.nvs)
            data = self.backend.load_nvs(self.num_nvs + 10)

        self.nvs = data
        self.load_module_info()

    def set_mode(self, mode):
        self.nvs[0] = mode
        self.backend.store_nvs(self.nvs)
        self.mode = mode

    def set_canid(self, canid):
        self.nvs[1] = canid
        self.backend.store_nvs(self.nvs)
        self.canid = canid

    def set_node_number(self, node_number):
        self.nvs[2] = int(node_number / 256)
        self.nvs[3] = node_number & 0xFF
        self.backend.store_nvs(self.nvs)
        self.node_number = node_number

    def find_existing_event(self, nn, en):
        # print(f'find_existing_event: {nn}, {en}')

        for i in range(self.num_events):
            offset = i * (self.event_size)

            if ((self.events[offset] * 256) + self.events[offset + 1]) == nn and (
                (self.events[offset + 2] * 256) + self.events[offset + 3]
            ) == en:
                # print(f'found event at index = {i}')
                return i

        print("event not found")
        return -1

    def find_event_space(self):
        # print('find_event_space')

        for i in range(self.num_events):
            offset = i * (self.event_size)

            if (
                self.events[offset] == 255
                and self.events[offset + 1] == 255
                and self.events[offset + 2] == 255
                and self.events[offset + 3] == 255
            ):
                return i

        return -1

    def read_event(self, index):
        # print('read_event')
        data = bytearray(self.event_size)
        offset = self.event_size * index

        for i in range(self.event_size):
            data[i] = self.events[offset + i]

        return data

    def write_event(self, nn, en, evnum, evval):
        # print('write_event')

        idx = self.find_existing_event(nn, en)

        if idx == -1:
            idx = self.find_event_space()

            if idx == -1:
                return False

        offset = idx * self.event_size
        self.events[offset] = int(nn / 256)
        self.events[offset + 1] = nn & 0xFF
        self.events[offset + 2] = int(en / 256)
        self.events[offset + 3] = en & 0xFF
        self.events[offset + 4 + (evnum - 1)] = evval

        self.backend.store_events(self.events)
        return True

    def read_event_ev(self, idx, evnum):
        # print('read_event_ev')
        offset = (idx * self.event_size) + 4 + (evnum - 1)
        return self.events[offset]

    def write_event_ev(self, idx, evnum, evval):
        # print('write_event_ev')
        offset = (idx * self.event_size) + 4 + (evnum - 1)
        self.events[offset] = evval
        self.backend.store_events(self.events)

    def clear_event(self, nn, en):
        # print('clear_event')

        idx = self.find_existing_event(nn, en)

        if idx == -1:
            return False

        for i in range(self.event_size):
            self.events[i + (idx * self.event_size)] = 255

        self.backend.store_events(self.events)
        return True

    def count_events(self):
        # print('count_events')

        count = 0

        for i in range(self.num_events):
            if sum(self.read_event(i)[0:4]) < 1020:
                count += 1

        return count

    def clear_all_events(self):
        self.events = bytearray((self.num_evs + 4) * self.num_events)
        self.backend.store_events(self.events)

    def read_nv(self, nvnum):
        return self.nvs[nvnum - 9]

    def write_nv(self, nvnum, value):
        self.nvs[nvnum + 9] = value
        self.backend.store_nvs(self.nvs)

    def load_module_info(self):
        self.mode = self.nvs[0]
        self.canid = self.nvs[1]
        self.node_number = (self.nvs[2] * 256) + self.nvs[3]

    def print_events(self, print_all=True):
        for i in range(self.num_events):
            if print_all or (self.events[i * self.event_size] < 0xFF):
                print(f"{i:3} = ", end="")
                for j in range(0, self.event_size):
                    print(f"{self.events[(i*self.event_size)+j]:3}", end=" ")
                print()

    def print_nvs(self):
        for i in range(self.num_nvs + 10):
            print(f"{i:2} - {self.nvs[i]}")

    def reboot(self):
        machine.soft_reset()

    def reset_module(self):
        print("** reset_module")
        self.nvs = bytearray(10 + self.num_nvs)
        self.events = bytearray((self.num_evs + 4) * self.num_events)

        self.backend.store_events(self.events)
        self.backend.store_nvs(self.nvs)

        self.reboot()

    def free_memory(self):
        gc.collect()
        return gc.mem_free()
