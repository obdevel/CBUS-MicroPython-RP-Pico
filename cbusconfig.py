
# cbusconfig.py

import machine

nvs_file_name = "/nvs.dat"
events_file_name = "/events.dat"

MODE_SLIM = 0
MODE_FLIM = 1
MODE_CHANGING = 2

class cbusconfig():
    
    def __init__(self, num_nvs=20, num_events=64, num_evs=4):
        print('** cbusconfig constructor')

        self.num_nvs = num_nvs
        self.num_events = num_events
        self.num_evs = num_evs
        self.ev_size = self.num_evs + 4

        self.nvs = bytearray(10 + self.num_nvs)
        self.events = bytearray((self.num_evs + 4) * self.num_events)
        self.params = bytearray(20)

        for i in range(len(self.events)):
            self.events[i] = 255;

        self.mode = 0
        self.canid = 0
        self.node_number = 0

    def begin(self):
        print('** cbusconfig begin')

        try:
            f = open(nvs_file_name, "r")
        except OSError:
            print('** initialising nvs')
            f = open(nvs_file_name, "w")
            f.write(self.nvs)
            f.close()
            f = open(nvs_file_name, "r")

        data = f.read()
        f.close()
        self.nvs = bytearray(data.encode("ascii"))

        try:
            f = open(events_file_name, "r")
        except OSError:
            print('** initialising events')
            f = open(events_file_name, "w")
            f.write(self.events)
            f.close()
            f = open(events_file_name, "r")

        data = f.read()
        f.close()
        self.events = bytearray(data.encode("ascii"))

        self.load_module_id()

    def write_changes(self):
        f = open(nvs_file_name, "w")
        f.write(self.nvs)
        f.close()

        f = open(events_file_name, "w")
        f.write(self.events)
        f.close()

    def set_mode(self, mode):
        self.nvs[0] = mode
        self.write_changes()
        self.mode = mode

    def set_canid(self, canid):
        self.nvs[1] = canid
        self.write_changes()
        self.canid = canid

    def set_node_number(self, node_number):
        self.nvs[2] = int(node_number / 256)
        self.nvs[3] = node_number & 0xff
        self.write_changes()
        self.node_number = node_number

    def find_existing_event(self, nn, en):
        print(f'find_existing_event, {nn}, {en}')

        for i in range(self.num_events):
            offset = i * (self.ev_size)

            if ((self.events[offset] * 256) + self.events[offset + 1]) == nn and ((self.events[offset + 2] * 256) + self.events[offset + 3]) == en:
                print(f'found event at index = {i}')
                return i

        print('event not found')
        return -1

    def find_event_space(self):
        print('find_event_space')

        for i in range(self.num_events):
            offset = i * (self.ev_size)

            if self.events[offset] == 255 and self.events[offset + 1] == 255 and self.events[offset + 2] == 255 and self.events[offset + 3] == 255:
                return i

        return -1

    def read_event(self, index):
        #print('read_event')
        data = bytearray(self.ev_size)
        offset = self.ev_size * index

        for i in range(self.ev_size):
            data[i] = self.events[offset + i]

        return data

    def write_event(self, nn, en, evnum, evval):
        #print('write_event')

        idx = self.find_existing_event(nn , en)

        if idx == -1:
            idx = self.find_event_space()

            if idx == -1:
                return False

        offset = idx * self.ev_size
        self.events[offset] = int(nn / 256)
        self.events[offset + 1] = nn & 0xff
        self.events[offset + 2] = int(en / 256)
        self.events[offset + 3] = en & 0xff
        self.events[offset + 4 + (evnum - 1)] = evval

        self.write_changes()
        return True

    def read_event_ev(self, idx, evnum):
        print('read_event_ev')
        offset = (idx * self.ev_size) + 4 + (evnum - 1)
        return self.events[offset]

    def write_event_ev(self, idx, evnum, evval):
        pass

    def clear_event(self, nn, en):
        print('clear_event')

        idx = self.config.find_existing_event(nn , en)

        if idx == -1:
            return False

        offset = idx * self.ev_size

        for i in range(self.ev_size):
            self.events[i] = 255

        return True

    def count_events(self):
        print('count_events')

        count = 0

        for i in range(self.num_events):
            if sum(self.read_event(i)[0:4]) < 1020:
                count += 1

        return count

    def clear_all_events(self):
        self.events = bytearray((self.num_evs + 4) * self.num_events)
        self.write_changes()

    def read_nv(self, nvnum):
        return self.nvs[nvnum - 10]

    def write_nv(self, nvnum, value):
        self.nvs[nvnum - 10] = value
        self.write_changes()

    def load_module_id(self):
        self.mode = self.nvs[0]
        self.canid = self.nvs[1]
        self.node_number = (self.nvs[2] * 256) + self.nvs[3]

    def reboot(self):
        machine.soft_reset()

    def reset_module(self):
        self.nvs = bytearray(10 + self.num_nvs)
        self.events = bytearray((self.num_evs + 4) * self.num_events)

        f = open(nvs_file_name, "w")
        f.write(self.nvs)
        f.close()
        f = open(events_file_name, "w")
        f.write(self.events)
        f.close()

        self.reboot()

    def free_memory(self):
        import gc
        gc.collect()
        return gc.mem_free()
