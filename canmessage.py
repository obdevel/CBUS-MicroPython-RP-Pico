
## canmessage.py

class canmessage:
    
    """ a class to represent a CAN frame """

    def __init__(self, id=0, len=0, data=bytearray(8), ext=False, rtr=False,):
        self.id = id
        self.len = len
        self.data = data
        self.ext = ext
        self.rtr = rtr

    def make_header(self, priority=0x0b):
        self.id |= (priority << 7)

    def print(self):
        print(f'[{self.id:x}] [{self.len}] ' + '[ ' + ' '.join('{:02x}'.format(x) for x in self.data) + ' ]')
