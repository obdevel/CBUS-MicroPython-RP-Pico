
## canmessage.py

class canmessage:
    
    """ a class to represent a CAN frame """

    def __init__(self, id=0, len=0, data=bytearray(8), rtr=False, ext=False):
        self.id = id
        self.len = len
        self.data = bytearray(data)
        self.ext = ext
        self.rtr = rtr

    def make_header(self, priority=0x0b):
        self.id |= (priority << 7)

    def get_canid(self):
        return self.id & 0x7f

    def print(self, hex=True):
        if hex:
            print(f'[{self.id:x}] [{self.len}] ' + '[ ' + ' '.join('{:02x}'.format(x) for x in self.data) + ' ]', end = '')
        else:
            print(f'[{self.id}] [{self.len}] ' + '[ ' + ' '.join('{:02}'.format(x) for x in self.data) + ' ]', end = '')

        print()
