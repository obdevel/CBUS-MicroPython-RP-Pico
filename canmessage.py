# canmessage.py

from micropython import const

import cbusdefs
import cbushistory
import logger

QUERY_UNKNOWN = const(-1)
QUERY_EVENTS = const(0)
QUERY_SHORTCODES = const(1)
QUERY_OPCODES = const(2)
QUERY_REGEX = const(3)
QUERY_ALL = const(4)

EVENT_OFF = const(0)
EVENT_ON = const(1)

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


def shortcode_to_tuple(code) -> tuple:
    pol = polarity_lookup.get(code[0])
    e = code.find("e")
    nn = int(code[2:e])
    en = int(code[e + 1:])
    return pol, nn, en


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
                f"[{self.id:x}] "
                + f"[{self.len:x}] [ "
                + " ".join("{:02x}".format(x) for x in self.data)
                + " ] "
                + rtr
                + ext
        )
        return str

    def make_header(self, priority=0x0b) -> None:
        self.id |= priority << 7

    def get_canid(self) -> int:
        return self.id & 0x7f

    def is_event(self) -> bool:
        return self.data[0] in event_opcodes

    def as_shortcode(self, either=False) -> str:
        nn = (self.data[1] * 256) + self.data[2]
        en = (self.data[3] * 256) + self.data[4]
        if either:
            code = "*n"
        else:
            code = "-n" if (self.data[0] & 1) else "+n"
        code += str(nn) + "e" + str(en)
        return code

    def as_tuple(self) -> tuple:
        nn = (self.data[1] * 256) + self.data[2]
        en = (self.data[3] * 256) + self.data[4]
        pol = 0 if self.data[0] & 1 else 1
        return pol, nn, en

    def get_node_number(self) -> int:
        return (self.data[1] * 256) + self.data[2]

    def get_event_number(self) -> int:
        return (self.data[3] * 256) + self.data[4]

    def get_node_and_event_numbers(self) -> tuple:
        return self.get_node_number(), self.get_event_number()

    # def set_opcode(self, opc) -> None:
    #     self.data[0] = opc
    #
    # def set_node_number(self, nn) -> None:
    #     self.data[1] = nn >> 256
    #     self.data[2] = nn & 0xff
    #
    # def set_event_number(self, en) -> None:
    #     self.data[3] = en >> 256
    #     self.data[4] = en & 0xff

    def print(self, hex_fmt=True) -> None:
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""

        if hex_fmt:
            print(
                f"[{self.id:x}] [{self.len:x}] "
                + "[ "
                + " ".join("{:02x}".format(x) for x in self.data)
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

    def matches(self, query, query_type=QUERY_ALL) -> bool:
        # self.logger.log(f"canmessage: match, query_type = {type}, query = {query}")

        if query_type == QUERY_EVENTS:
            return self.as_tuple() in query
        elif query_type == QUERY_SHORTCODES:
            return self.as_shortcode() in query
        elif query_type == QUERY_OPCODES:
            return self.data[0] in query
        elif query_type == QUERY_REGEX:
            return True
        elif query_type == QUERY_ALL:
            return True
        else:
            return False


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

    def from_message(self, msg) -> None:
        self.len = msg.len
        self.data = msg.data
        self.nn = (msg.data[1] * 256) + msg.data[2]
        self.en = (msg.data[3] * 256) + msg.data[4]

    def make_event(self, opcode) -> None:
        self.len = 5
        self.data = bytearray([opcode, self.nn >> 8, self.nn & 0xff, self.en >> 8, self.en & 0xff])

    def send_on(self) -> None:
        opcode = cbusdefs.OPC_ACON if self.is_long else cbusdefs.OPC_ASON
        self.make_event(opcode)
        self.cbus.send_cbus_message(self)
        self.state = EVENT_ON

    def send_off(self) -> None:
        opcode = cbusdefs.OPC_ACOF if self.is_long else cbusdefs.OPC_ASOF
        self.make_event(opcode)
        self.cbus.send_cbus_message(self)
        self.state = EVENT_OFF

    def get_state(self) -> int:
        return self.state

    def from_event_table(self, idx=0) -> canmessage:
        pass
