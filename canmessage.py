
## canmessage.py

class canmessage:
    
    """ a class to represent a CAN frame """

    def __init__(self, id=0, len=0, data=bytearray(8), rtr=False, ext=False):
        self.id = id
        self.len = len
        self.data = bytearray(data)
        self.ext = ext
        self.rtr = rtr

    def __str__(self):
        rtr = 'r' if self.rtr else ''
        ext = 'x' if self.ext else ''
        ch = f'[{self.id:x}] ' + f'[{self.len:x}] [ ' + ' '.join('{:02x}'.format(x) for x in self.data) + ' ] ' + rtr + ext
        return ch

    def make_header(self, priority=0x0b):
        if (self.id - self.get_canid() == 0):
            self.id |= (priority << 7)

    def get_canid(self):
        return self.id & 0x7f

    def print(self, hex=True):
        rtr = 'r' if self.rtr else ''
        ext = 'x' if self.ext else ''

        if hex:
            print(f'[{self.id:x}] [{self.len:x}] ' + '[ ' + ' '.join('{:02x}'.format(x) for x in self.data) + ' ] ' + rtr + ext, end = '')
        else:
            print(f'[{self.id}] [{self.len}] ' + '[ ' + ' '.join('{:02}'.format(x) for x in self.data) + ' ] ' + rtr + ext, end = '')

        print()
