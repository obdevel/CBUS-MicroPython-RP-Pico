# canmessage.py

import re
import cbusconfig
import cbusdefs
import cbushistory
import logger

QUERY_UNKNOWN = -1
QUERY_TUPLE = 1
QUERY_SHORTCODE = 2
QUERY_OPCODE = 3
QUERY_REGEX = 4
QUERY_ALL = 5

EVENT_OFF = 0
EVENT_ON = 1

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
        self.logger = logger.logger()
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

    def matches(self, type=QUERY_ALL, query=None):
        # self.logger.log(f"canmessage: match, type = {type}, query = {query}")

        if type == QUERY_UNKNOWN:
            return False
        elif type == QUERY_TUPLE:
            return True
        elif type == QUERY_SHORTCODE:
            return True
        elif type == QUERY_OPCODE:
            return True
        elif type == QUERY_REGEX:
            return True
        elif type == QUERY_ALL:
            return True
        else:
            return False

    def get_node_number(self):
        return (self.data[1] * 256) + self.data[2]

    def get_event_number(self):
        return (self.data[3] * 256) + self.data[4]

    def get_node_and_event_numbers(self):
        return self.get_node_number(), self.get_event_number()

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


class cbusevent(canmessage):
    def __init__(self, cbus, is_long=True, nn=0, en=0, state=EVENT_OFF, addbytes=None, send_now=False):
        super().__init__()
        self.cbus = cbus
        self.is_long = is_long
        self.nn = nn
        self.en = en
        self.state = state
        self.addbytes = addbytes

        if send_now:
            if self.state == EVENT_ON:
                self.send_on()
            elif self.state == EVENT_OFF:
                self.send_off()

    def make_event(self, opcode):
        self.len = 5
        self.data = bytearray([opcode, self.nn >> 8, self.nn & 0xff, self.en >> 8, self.en & 0xff])

    def send_on(self):
        self.make_event(cbusdefs.OPC_ACON)
        self.cbus.send_cbus_message(self)
        self.state = EVENT_ON

    def send_off(self):
        self.make_event(cbusdefs.OPC_ACOF)
        self.cbus.send_cbus_message(self)
        self.state = EVENT_OFF

    def get_state(self):
        return self.state

    def from_event_table(self, idx=0):
        pass

