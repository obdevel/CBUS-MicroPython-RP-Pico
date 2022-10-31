# canmessage.py

import cbusdefs
import cbushistory

event_opcodes = (
    cbusdefs.OPC_ACON,
    cbusdefs.OPC_ACOF,
    cbusdefs.OPC_ASON,
    cbusdefs.OPC_ASOF,
    cbusdefs.OPC_ACON1,
    cbusdefs.OPC_ACOF1,
    cbusdefs.OPC_ASON1,
    cbusdefs.OPC_ASOF1,
    cbusdefs.OPC_ACON2,
    cbusdefs.OPC_ACOF2,
    cbusdefs.OPC_ASON2,
    cbusdefs.OPC_ASOF2,
    cbusdefs.OPC_ACON3,
    cbusdefs.OPC_ACOF3,
    cbusdefs.OPC_ASON3,
    cbusdefs.OPC_ASOF3
)

polarity_lookup = {
    "*": cbushistory.POLARITY_EITHER,
    "+": cbushistory.POLARITY_ON,
    "-": cbushistory.POLARITY_OFF,
    "?": cbushistory.POLARITY_UNKNOWN
}

def shortcode_to_tuple(code):
    pol = polarity_lookup.get(code[0])
    e = code.find("e")
    nn = int(code[2:e])
    en = int(code[e+1:])
    return (pol, nn, en)


class canmessage:

    """a class to represent a CAN frame"""

    def __init__(self, id=0, len=0, data=bytearray(8), rtr=False, ext=False):
        self.id = id
        self.len = len
        self.data = bytearray(data)
        self.ext = ext
        self.rtr = rtr

    def __str__(self):
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""
        str = (
            f"[{self.id:X}] "
            + f"[{self.len:X}] [ "
            + " ".join("{:02X}".format(x) for x in self.data)
            + " ] "
            + rtr
            + ext
        )
        return str

    def make_header(self, priority=0x0B):
        if self.id - self.get_canid() == 0:
            self.id |= priority << 7

    def get_canid(self):
        return self.id & 0x7F

    def is_event(self):
        return self.data[0] in event_opcodes

    def as_shortcode(self, either=False):
        nn = (self.data[1] * 256) + self.data[2]
        en = (self.data[3] * 256) + self.data[4]
        if either:
            code = "*n"
        else:
            code = "-n" if (self.data[0] & 1) else "+n"
        code += str(nn) + "e" + str(en)
        return code

    def as_tuple(self):
        nn = (self.data[1] * 256) + self.data[2]
        en = (self.data[3] * 256) + self.data[4]
        pol = 0 if self.data[0] & 1 else 1
        return (pol, nn, en)

    def print(self, hex=True):
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""

        if hex:
            print(
                f"[{self.id:X}] [{self.len:X}] "
                + "[ "
                + " ".join("{:02X}".format(x) for x in self.data)
                + " ] "
                + rtr
                + ext,
                end="",
            )
        else:
            print(
                f"[{self.id}] [{self.len}] "
                + "[ "
                + " ".join("{:02}".format(x) for x in self.data)
                + " ] "
                + rtr
                + ext,
                end="",
            )

        print()
