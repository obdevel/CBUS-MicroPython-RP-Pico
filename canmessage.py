# canmessage.py

from micropython import const

import cbus
import cbusdefs
import logger

NO_OPCODE = const(0)

POLARITY_UNKNOWN = const(-1)
POLARITY_OFF = const(0)
POLARITY_ON = const(1)
POLARITY_EITHER = const(2)

QUERY_UNKNOWN = const(-1)
QUERY_TUPLE = const(20)
QUERY_TUPLES = const(0)
QUERY_SHORTCODES = const(1)
QUERY_OPCODES = const(2)
QUERY_REGEX = const(3)
QUERY_CANID = const(4)
QUERY_RTR = const(5)
QUERY_EXT = const(6)
QUERY_EVENTS = const(7)
QUERY_ALL_EVENTS = const(8)
QUERY_LONG_MESSAGES = const(9)
QUERY_UDF = const(10)
QUERY_ALL = const(11)
QUERY_NONE = const(12)
QUERY_NN = const(13)
QUERY_DN = const(14)

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
    cbusdefs.OPC_ASOF3,
    cbusdefs.OPC_ARON,
    cbusdefs.OPC_AROF,
    cbusdefs.OPC_ARSON,
    cbusdefs.OPC_ARSOF,
    cbusdefs.OPC_ARON1,
    cbusdefs.OPC_AROF1,
    cbusdefs.OPC_ARSON1,
    cbusdefs.OPC_ARSOF1,
    cbusdefs.OPC_ARON2,
    cbusdefs.OPC_AROF2,
    cbusdefs.OPC_ARSON2,
    cbusdefs.OPC_ARSOF2,
    cbusdefs.OPC_ARON3,
    cbusdefs.OPC_AROF3,
    cbusdefs.OPC_ARSON3,
    cbusdefs.OPC_ARSOF3
)

event_opcodes_lookup = (
    ((cbusdefs.OPC_ACOF, cbusdefs.OPC_ACON), (cbusdefs.OPC_ASOF, cbusdefs.OPC_ASON)),
    ((cbusdefs.OPC_ACOF1, cbusdefs.OPC_ACON1), (cbusdefs.OPC_ASOF1, cbusdefs.OPC_ASON1)),
    ((cbusdefs.OPC_ACOF2, cbusdefs.OPC_ACON2), (cbusdefs.OPC_ASOF2, cbusdefs.OPC_ASON2)),
    ((cbusdefs.OPC_ACOF3, cbusdefs.OPC_ACON3), (cbusdefs.OPC_ASOF3, cbusdefs.OPC_ASON3))
)

polarity_lookup = {
    "*": POLARITY_EITHER,
    "+": POLARITY_ON,
    "-": POLARITY_OFF,
    "?": POLARITY_UNKNOWN
}


def shortcode_to_tuple(code) -> tuple:
    polarity = polarity_lookup.get(code[0])
    e = code.find("e")
    nn = int(code[2:e])
    en = int(code[e + 1:])
    return polarity, nn, en


class canmessage:
    def __init__(self, canid: int = 0, dlc: int = 0, data=bytearray(8), rtr: bool = False, ext: bool = False):
        self.logger = logger.logger()
        self.canid = canid
        self.make_header()
        self.dlc = dlc
        self.data = bytearray(data)
        self.rtr = rtr
        self.ext = ext

    def __str__(self):
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""
        cstr = (
                f"[{self.canid:x}] "
                + f"[{self.dlc:x}] [ "
                + " ".join("{:02x}".format(x) for x in self.data[:self.dlc])
                + " ] "
                + rtr
                + ext
        )
        return cstr

    def __iter__(self):
        if self.dlc > 0:
            if self.is_event():
                self.polarity = 0 if self.data[0] & 1 else 1
                for x in self.polarity, self.get_node_number(), self.get_event_number():
                    yield x
            else:
                for x in self.data[:self.dlc]:
                    yield x

    def make_header(self, priority=0x0b) -> None:
        self.canid = (priority << 7) + self.get_canid()

    def get_canid(self) -> int:
        return self.canid & 0x7f

    def is_event(self) -> bool:
        return self.data[0] in event_opcodes

    def as_shortcode(self, either=False) -> str:
        nn = self.get_node_number()
        en = self.get_event_number()
        if either:
            code = "*n"
        else:
            code = "-n" if (self.data[0] & 1) else "+n"
        code += str(nn) + "e" + str(en)
        return code

    def get_node_number(self) -> int:
        return (self.data[1] << 8) + (self.data[2] & 0xff)

    def get_event_number(self) -> int:
        return (self.data[3] << 8) + (self.data[4] & 0xff)

    def get_node_and_event_numbers(self) -> tuple:
        return self.get_node_number(), self.get_event_number(),

    def print(self, hex_fmt=True) -> None:
        rtr = "R" if self.rtr else ""
        ext = "X" if self.ext else ""

        if hex_fmt:
            print(
                f"[{self.canid:x}] [{self.dlc:x}] "
                + "[ "
                + " ".join("{:02x}".format(x) for x in self.data[:self.dlc])
                + " ] "
                + rtr
                + ext,
                end="",
            )
        else:
            print(
                f"[{self.canid}] [{self.dlc}] "
                + "[ "
                + " ".join("{:02}".format(x) for x in self.data[:self.dlc])
                + " ] "
                + rtr
                + ext,
                end="",
            )

        print()

    def matches(self, query_type: int = QUERY_ALL, query=None) -> bool:
        if query_type in (QUERY_TUPLES, QUERY_TUPLE):
            if isinstance(query, tuple):
                if isinstance(query[0], tuple):
                    return tuple(self) in query
                else:
                    return tuple(self) == query
            else:
                self.logger.log(f'matches: expected tuple as query, query = {query}')
                return False
        elif query_type == QUERY_SHORTCODES:
            return self.as_shortcode() in query
        elif query_type == QUERY_OPCODES:
            return self.data[0] in query
        elif query_type == QUERY_REGEX:
            return True
        elif query_type == QUERY_CANID:
            return self.get_canid() == query
        elif query_type == QUERY_RTR:
            return self.rtr
        elif query_type == QUERY_EXT:
            return self.ext
        elif query_type == QUERY_EVENTS:
            return self.data[0] in query
        elif query_type == QUERY_ALL_EVENTS:
            return self.is_event()
        elif query_type == QUERY_LONG_MESSAGES:
            return self.data[0] == cbusdefs.OPC_DTXC
        elif query_type == QUERY_UDF:
            return query(self)
        elif query_type == QUERY_ALL:
            return True
        elif query_type == QUERY_NN:
            return self.get_node_number() == query
        elif query_type == QUERY_DN:
            return self.get_event_number() == query
        else:
            return False


class cbusevent(canmessage):
    def __init__(self, cbus: cbus.cbus, polarity: int = POLARITY_OFF, nn: int = 0, en: int = 0, send_now: bool = False):
        super().__init__(dlc=5)
        self.cbus = cbus
        self.nn = nn
        self.en = en
        self.polarity = polarity
        self.sync_data(0)

        if send_now:
            self.send()

    def sync_data(self, opcode: int) -> None:
        self.data = bytearray([opcode, self.nn >> 8, self.nn & 0xff, self.en >> 8, self.en & 0xff])

    def send(self) -> None:
        if self.polarity == POLARITY_ON:
            self.send_on()
        elif self.polarity == POLARITY_OFF:
            self.send_off()

    def send_on(self) -> None:
        self.polarity = POLARITY_ON
        self.sync_data(self.calc_opcode())
        self.cbus.send_cbus_message(self)

    def send_off(self) -> None:
        self.polarity = POLARITY_OFF
        self.sync_data(self.calc_opcode())
        self.cbus.send_cbus_message(self)

    def calc_opcode(self) -> int:
        add_bytes = self.dlc - 5
        evt_length = self.nn == 0
        return event_opcodes_lookup[add_bytes][evt_length][self.polarity]


def message_from_tuple(t: tuple) -> canmessage:
    msg = canmessage()
    tlen = len(t)
    msg.dlc = 5 if tlen == 3 else tlen

    if tlen == 3:
        if t[0] == 0:
            msg.data[0] = cbusdefs.OPC_ACOF if t[1] else cbusdefs.OPC_ASOF
        elif t[0] == 1:
            msg.data[0] = cbusdefs.OPC_ACON if t[1] else cbusdefs.OPC_ASON
        else:
            msg.data[0] = t[0]

        msg.data[1] = t[1] >> 8
        msg.data[2] = t[1] & 0xff
        msg.data[3] = t[2] >> 8
        msg.data[4] = t[2] & 0xff
    else:
        msg.data = bytearray(t)

    return msg


def event_from_message(cbus: cbus.cbus, msg: canmessage) -> cbusevent:
    evt = cbusevent(cbus)
    evt.canid = cbus.config.canid if msg.canid == 0 else msg.canid
    # evt.dlc = 5
    evt.polarity = POLARITY_OFF if msg.data[0] & 1 else POLARITY_ON
    for i in range(evt.dlc):
        evt.data[i] = msg.data[i]
    evt.data[0] = evt.calc_opcode()
    evt.nn = msg.get_node_number()
    evt.en = msg.get_event_number()

    return evt


def event_from_tuple(cbus: cbus.cbus, t: tuple) -> cbusevent:
    msg = message_from_tuple(t)
    evt = event_from_message(cbus, msg)
    evt.canid = cbus.config.canid
    # evt.dlc = 5
    evt.polarity = t[0]
    evt.nn = t[1]
    evt.en = t[2]
    evt.sync_data(evt.calc_opcode())

    return evt


def event_from_table(cbus: cbus.cbus, idx: int) -> canmessage:
    evt = cbusevent(cbus)
    evt.canid = cbus.config.canid
    evdata = cbus.config.read_event(idx)
    for i in range(4):
        evt.data[i + 1] = evdata[i]
    evt.data[0] = evt.calc_opcode()
    evt.dlc = 5
    evt.polarity = POLARITY_UNKNOWN
    evt.nn = evt.get_node_number()
    evt.en = evt.get_event_number()

    return evt


def tuple_from_tuples(events: tuple, which: int) -> tuple | None:
    t = None
    try:
        t = events[which]
    except IndexError:
        t = None
    finally:
        return t
