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
QUERY_CANID = const(4)
QUERY_ALL = const(5)

EVENT_EITHER = cbushistory.POLARITY_EITHER
EVENT_OFF = cbushistory.POLARITY_OFF
EVENT_ON = cbushistory.POLARITY_ON
EVENT_UNKNOWN = cbushistory.POLARITY_UNKNOWN

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
    "*": EVENT_EITHER,
    "+": EVENT_ON,
    "-": EVENT_OFF,
    "?": EVENT_UNKNOWN
}


def shortcode_to_tuple(code) -> tuple:
    pol = polarity_lookup.get(code[0])
    e = code.find("e")
    nn = int(code[2:e])
    en = int(code[e + 1:])
    return pol, nn, en


class canmessage:
    """a class to represent a CAN frame"""

    def __init__(self, canid=0, dlc=0, data=bytearray(8), rtr=False, ext=False):
        self.logger = logger.logger()
        self.canid = canid
        self.dlc = dlc
        self.data = bytearray(data)
        self.ext = ext
        self.rtr = rtr

    def __str__(self):
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""
        cstr = (
                f"[{self.canid:x}] "
                + f"[{self.dlc:x}] [ "
                + " ".join("{:02x}".format(x) for x in self.data)
                + " ] "
                + rtr
                + ext
        )
        return cstr

    def make_header(self, priority=0x0b) -> None:
        self.canid |= priority << 7

    def get_canid(self) -> int:
        return self.canid & 0x7f

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
        if self.data[0] in event_opcodes:
            nn = (self.data[1] * 256) + self.data[2]
            en = (self.data[3] * 256) + self.data[4]
            pol = 0 if self.data[0] & 1 else 1
            return pol, nn, en
        else:
            return tuple(self.data)

    def __iter__(self):
        if self.data[0] in event_opcodes:
            nn = (self.data[1] * 256) + self.data[2]
            en = (self.data[3] * 256) + self.data[4]
            pol = 0 if self.data[0] & 1 else 1
            for x in range(3):
                if x == 0:
                    yield pol
                elif x == 1:
                    yield nn
                else:
                    yield en
        else:
            for x in range(self.dlc):
                yield self.data[x]

    def get_node_number(self) -> int:
        return (self.data[1] * 256) + self.data[2]

    def get_event_number(self) -> int:
        return (self.data[3] * 256) + self.data[4]

    def get_node_and_event_numbers(self) -> tuple:
        return self.get_node_number(), self.get_event_number()

    def print(self, hex_fmt=True) -> None:
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""

        if hex_fmt:
            print(
                f"[{self.canid:x}] [{self.dlc:x}] "
                + "[ "
                + " ".join("{:02x}".format(x) for x in self.data)
                + " ] "
                + rtr
                + ext,
                end="",
            )
        else:
            print(
                f"[{self.canid}] [{self.dlc}] "
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
            return tuple(self) in query
        elif query_type == QUERY_SHORTCODES:
            return self.as_shortcode() in query
        elif query_type == QUERY_OPCODES:
            return self.data[0] in query
        elif query_type == QUERY_REGEX:
            return True
        elif query_type == QUERY_CANID:
            return self.get_canid() == query
        elif query_type == QUERY_ALL:
            return True
        else:
            return False


class cbusevent(canmessage):
    """a class to represent a CBUS event"""

    def __init__(self, cbus, nn=0, en=0, pol=EVENT_OFF, send_now=False):
        super().__init__()
        self.cbus = cbus
        self.nn = nn
        self.en = en
        self.pol = pol

        if send_now:
            self.send()

    def from_message(self, msg):
        self.pol = EVENT_OFF if msg.data[0] & 1 else EVENT_ON
        self.nn = msg.get_node_number()
        self.en = msg.get_event_number()
        self.make_event(msg.data[0])
        return self

    def send(self) -> None:
        if self.pol == EVENT_ON:
            self.send_on()
        elif self.pol == EVENT_OFF:
            self.send_off()

    def make_event(self, opcode) -> None:
        self.dlc = 5
        self.data = bytearray([opcode, self.nn >> 8, self.nn & 0xff, self.en >> 8, self.en & 0xff])

    def send_on(self) -> None:
        opcode = cbusdefs.OPC_ACON if self.nn > 0 else cbusdefs.OPC_ASON
        self.make_event(opcode)
        self.cbus.send_cbus_message(self)
        self.pol = EVENT_ON

    def send_off(self) -> None:
        opcode = cbusdefs.OPC_ACOF if self.nn > 0 else cbusdefs.OPC_ASOF
        self.make_event(opcode)
        self.cbus.send_cbus_message(self)
        self.pol = EVENT_OFF

    def from_event_table(self, idx=0) -> canmessage:
        pass


def msg_from_tuple(t: tuple) -> canmessage:
    msg = canmessage()
    msg.dlc = 5

    if t[0] == 0:
        msg.data[0] = cbusdefs.OPC_ACOF if t[1] else cbusdefs.OPC_ASOF
    elif t[1] == 1:
        msg.data[0] = cbusdefs.OPC_ACON if t[1] else cbusdefs.OPC_ASON
    else:
        msg.data[0] = t[0]

    msg.data[1] = t[1] >> 8
    msg.data[2] = t[1] & 0xff
    msg.data[3] = t[2] >> 8
    msg.data[4] = t[2] & 0xff
    return msg


def event_from_tuple(cbus, t: tuple) -> cbusevent:
    evt = cbusevent(cbus)
    evt.pol = t[0]
    evt.nn = t[1]
    evt.en = t[2]
    return evt


def event_from_message(cbus, msg: canmessage) -> cbusevent:
    evt = cbusevent(cbus)
    evt.pol = EVENT_OFF if msg.data[0] & 1 else EVENT_ON
    evt.nn = msg.get_node_number()
    evt.en = msg.get_event_number()
    return evt
