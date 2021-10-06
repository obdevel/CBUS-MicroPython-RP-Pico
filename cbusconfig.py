
# cbusconfig.py

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
        
        self.load_id()
        
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
        self.nvs[2] = int(node_number / 255)
        self.nvs[3] = node_number & 0xff
        self.write_changes()
        self.node_number = node_number

    def find_existing_event(self, nn, en):
        pass

    def find_event_space(self):
        pass

    def write_event(self, index, data):
        begin = self.ev_size * index

        for i in range(self.ev_size):
            self.events[begin + i] = data[i]

        self.write_changes()

    def read_event(self, index):
        data = bytearray(self.ev_size)
        begin = self.ev_size * index

        for i in range(self.ev_size):
            data[i] = self.events[begin + i]

        return data

    def get_event_ev_val(self, idx, evnum):
        offset = ((self.ev_size + 4) * index) + evnum
        return self.events(offset)

    def num_events(self):
        pass

    def read_nv(self, nvnum):
        return self.nvs[nvnum - 10]

    def write_nv(self, nvnum, value):
        self.nvs[nvnum - 10] = value
        self.write_changes()

    def load_id(self):
        self.mode = self.nvs[0]
        self.canid = self.nvs[1]
        self.node_number = (self.nvs[2] >> 8) + self.nvs[3]

    def reset_module(self):
        pass
    
    
    