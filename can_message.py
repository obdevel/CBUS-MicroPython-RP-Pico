
## can_message.py

class can_message:
    
    """ a class to represent a CAN frame """

    def __init__(self, id=0, len=0, data=bytearray(8), ext=False, rtr=False,):
        self.id = id
        self.len = len
        self.data = data
        self.ext = ext
        self.rtr = ext

    def make_header(self, priority=0x0b):
        self.id |= (priority << 7)

