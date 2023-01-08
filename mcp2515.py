import collections
import sys
import time

import uasyncio as asyncio
from machine import Pin, SPI
from micropython import const

import canio
import canmessage
import circularQueue
import logger


# class CAN_CLOCK:
#     MCP_20MHZ = 1
#     MCP_16MHZ = 2
#     MCP_8MHZ = 3
#
#
# class CAN_SPEED:
#     CAN_5KBPS = 1
#     CAN_10KBPS = 2
#     CAN_20KBPS = 3
#     CAN_31K25BPS = 4
#     CAN_33KBPS = 5
#     CAN_40KBPS = 6
#     CAN_50KBPS = 7
#     CAN_80KBPS = 8
#     CAN_83K3BPS = 9
#     CAN_95KBPS = 10
#     CAN_100KBPS = 11
#     CAN_125KBPS = 12
#     CAN_200KBPS = 13
#     CAN_250KBPS = 14
#     CAN_500KBPS = 15
#     CAN_1000KBPS = 16


# class CAN_CLKOUT:
#     CLKOUT_DISABLE = const(-1)
#     CLKOUT_DIV1 = const(0x0)
#     CLKOUT_DIV2 = const(0x1)
#     CLKOUT_DIV4 = const(0x2)
#     CLKOUT_DIV8 = const(0x3)


class ERROR:
    ERROR_OK = const(0)
    ERROR_FAIL = const(1)
    ERROR_ALLTXBUSY = const(2)
    ERROR_FAILINIT = const(3)
    ERROR_FAILTX = const(4)
    ERROR_NOMSG = const(5)


class MASK:
    MASK0 = const(1)
    MASK1 = const(2)


class RXF:
    RXF0 = const(0)
    RXF1 = const(1)
    RXF2 = const(2)
    RXF3 = const(3)
    RXF4 = const(4)
    RXF5 = const(5)


class RXBn:
    RXB0 = const(0)
    RXB1 = const(1)


class TXBn:
    TXB0 = const(0)
    TXB1 = const(1)
    TXB2 = const(2)


class CANINTF:
    CANINTF_RX0IF = const(0x01)
    CANINTF_RX1IF = const(0x02)
    CANINTF_TX0IF = const(0x04)
    CANINTF_TX1IF = const(0x08)
    CANINTF_TX2IF = const(0x10)
    CANINTF_ERRIF = const(0x20)
    CANINTF_WAKIF = const(0x40)
    CANINTF_MERRF = const(0x80)


class EFLG:
    EFLG_RX1OVR = const(1 << 7)
    EFLG_RX0OVR = const(1 << 6)
    EFLG_TXBO = const(1 << 5)
    EFLG_TXEP = const(1 << 4)
    EFLG_RXEP = const(1 << 3)
    EFLG_TXWAR = const(1 << 2)
    EFLG_RXWAR = const(1 << 1)
    EFLG_EWARN = const(1 << 0)


CANCTRL_REQOP = const(0xE0)
CANCTRL_ABAT = const(0x10)
CANCTRL_OSM = const(0x08)
CANCTRL_CLKEN = const(0x04)
CANCTRL_CLKPRE = const(0x03)


class CANCTRL_REQOP_MODE:
    CANCTRL_REQOP_NORMAL = const(0x00)
    CANCTRL_REQOP_SLEEP = const(0x20)
    CANCTRL_REQOP_LOOPBACK = const(0x40)
    CANCTRL_REQOP_LISTENONLY = const(0x60)
    CANCTRL_REQOP_CONFIG = const(0x80)
    CANCTRL_REQOP_POWERUP = const(0xE0)


CANSTAT_OPMOD = const(0xE0)
CANSTAT_ICOD = const(0x0E)

# CNF3_SOF = const(0x80)

TXB_EXIDE_MASK = const(0x08)
DLC_MASK = const(0x0F)
RTR_MASK = const(0x40)

RXBnCTRL_RXM_STD = const(0x20)
RXBnCTRL_RXM_EXT = const(0x40)
RXBnCTRL_RXM_STDEXT = const(0x00)
RXBnCTRL_RXM_MASK = const(0x60)
RXBnCTRL_RTR = const(0x08)
RXB0CTRL_BUKT = const(0x04)
RXB0CTRL_FILHIT_MASK = const(0x03)
RXB1CTRL_FILHIT_MASK = const(0x07)
RXB0CTRL_FILHIT = const(0x00)
RXB1CTRL_FILHIT = const(0x01)

MCP_SIDH = const(0)
MCP_SIDL = const(1)
MCP_EID8 = const(2)
MCP_EID0 = const(3)
MCP_DLC = const(4)
MCP_DATA = const(5)


class STAT:
    STAT_RX0IF = const(1 << 0)
    STAT_RX1IF = const(1 << 1)


STAT_RXIF_MASK = STAT.STAT_RX0IF | STAT.STAT_RX1IF


class TXBnCTRL:
    TXB_ABTF = const(0x40)
    TXB_MLOA = const(0x20)
    TXB_TXERR = const(0x10)
    TXB_TXREQ = const(0x08)
    TXB_TXIE = const(0x04)
    TXB_TXP = const(0x03)


EFLG_ERRORMASK = (
        EFLG.EFLG_RX1OVR
        | EFLG.EFLG_RX0OVR
        | EFLG.EFLG_TXBO
        | EFLG.EFLG_TXEP
        | EFLG.EFLG_RXEP
)


class INSTRUCTION:
    INSTRUCTION_WRITE = const(0x02)
    INSTRUCTION_READ = const(0x03)
    INSTRUCTION_BITMOD = const(0x05)
    INSTRUCTION_LOAD_TX0 = const(0x40)
    INSTRUCTION_LOAD_TX1 = const(0x42)
    INSTRUCTION_LOAD_TX2 = const(0x44)
    INSTRUCTION_RTS_TX0 = const(0x81)
    INSTRUCTION_RTS_TX1 = const(0x82)
    INSTRUCTION_RTS_TX2 = const(0x84)
    INSTRUCTION_RTS_ALL = const(0x87)
    INSTRUCTION_READ_RX0 = const(0x90)
    INSTRUCTION_READ_RX1 = const(0x94)
    INSTRUCTION_READ_STATUS = const(0xA0)
    INSTRUCTION_RX_STATUS = const(0xB0)
    INSTRUCTION_RESET = const(0xC0)


class REGISTER:
    MCP_RXF0SIDH = const(0x00)
    MCP_RXF0SIDL = const(0x01)
    MCP_RXF0EID8 = const(0x02)
    MCP_RXF0EID0 = const(0x03)
    MCP_RXF1SIDH = const(0x04)
    MCP_RXF1SIDL = const(0x05)
    MCP_RXF1EID8 = const(0x06)
    MCP_RXF1EID0 = const(0x07)
    MCP_RXF2SIDH = const(0x08)
    MCP_RXF2SIDL = const(0x09)
    MCP_RXF2EID8 = const(0x0A)
    MCP_RXF2EID0 = const(0x0B)
    MCP_CANSTAT = const(0x0E)
    MCP_CANCTRL = const(0x0F)
    MCP_RXF3SIDH = const(0x10)
    MCP_RXF3SIDL = const(0x11)
    MCP_RXF3EID8 = const(0x12)
    MCP_RXF3EID0 = const(0x13)
    MCP_RXF4SIDH = const(0x14)
    MCP_RXF4SIDL = const(0x15)
    MCP_RXF4EID8 = const(0x16)
    MCP_RXF4EID0 = const(0x17)
    MCP_RXF5SIDH = const(0x18)
    MCP_RXF5SIDL = const(0x19)
    MCP_RXF5EID8 = const(0x1A)
    MCP_RXF5EID0 = const(0x1B)
    MCP_TEC = const(0x1C)
    MCP_REC = const(0x1D)
    MCP_RXM0SIDH = const(0x20)
    MCP_RXM0SIDL = const(0x21)
    MCP_RXM0EID8 = const(0x22)
    MCP_RXM0EID0 = const(0x23)
    MCP_RXM1SIDH = const(0x24)
    MCP_RXM1SIDL = const(0x25)
    MCP_RXM1EID8 = const(0x26)
    MCP_RXM1EID0 = const(0x27)
    MCP_CNF3 = const(0x28)
    MCP_CNF2 = const(0x29)
    MCP_CNF1 = const(0x2A)
    MCP_CANINTE = const(0x2B)
    MCP_CANINTF = const(0x2C)
    MCP_EFLG = const(0x2D)
    MCP_TXB0CTRL = const(0x30)
    MCP_TXB0SIDH = const(0x31)
    MCP_TXB0SIDL = const(0x32)
    MCP_TXB0EID8 = const(0x33)
    MCP_TXB0EID0 = const(0x34)
    MCP_TXB0DLC = const(0x35)
    MCP_TXB0DATA = const(0x36)
    MCP_TXB1CTRL = const(0x40)
    MCP_TXB1SIDH = const(0x41)
    MCP_TXB1SIDL = const(0x42)
    MCP_TXB1EID8 = const(0x43)
    MCP_TXB1EID0 = const(0x44)
    MCP_TXB1DLC = const(0x45)
    MCP_TXB1DATA = const(0x46)
    MCP_TXB2CTRL = const(0x50)
    MCP_TXB2SIDH = const(0x51)
    MCP_TXB2SIDL = const(0x52)
    MCP_TXB2EID8 = const(0x53)
    MCP_TXB2EID0 = const(0x54)
    MCP_TXB2DLC = const(0x55)
    MCP_TXB2DATA = const(0x56)
    MCP_RXB0CTRL = const(0x60)
    MCP_RXB0SIDH = const(0x61)
    MCP_RXB0SIDL = const(0x62)
    MCP_RXB0EID8 = const(0x63)
    MCP_RXB0EID0 = const(0x64)
    MCP_RXB0DLC = const(0x65)
    MCP_RXB0DATA = const(0x66)
    MCP_RXB1CTRL = const(0x70)
    MCP_RXB1SIDH = const(0x71)
    MCP_RXB1SIDL = const(0x72)
    MCP_RXB1EID8 = const(0x73)
    MCP_RXB1EID0 = const(0x74)
    MCP_RXB1DLC = const(0x75)
    MCP_RXB1DATA = const(0x76)


N_TXBUFFERS = const(3)
N_RXBUFFERS = const(2)

# CAN_CFGS = {
#     CAN_CLOCK.MCP_8MHZ: {
#         CAN_SPEED.CAN_125KBPS: [
#             MCP_8MHz_125kBPS_CFG1,
#             MCP_8MHz_125kBPS_CFG2,
#             MCP_8MHz_125kBPS_CFG3,
#         ],
#     },
#     CAN_CLOCK.MCP_16MHZ: {
#         CAN_SPEED.CAN_125KBPS: [
#             MCP_16MHz_125kBPS_CFG1,
#             MCP_16MHz_125kBPS_CFG2,
#             MCP_16MHz_125kBPS_CFG3,
#         ],
#     },
# }

# speed 8M
MCP_8MHz_125kBPS_CFG1 = const(0x01)
MCP_8MHz_125kBPS_CFG2 = const(0xB1)
MCP_8MHz_125kBPS_CFG3 = const(0x85)

# speed 16M
MCP_16MHz_125kBPS_CFG1 = const(0x03)
MCP_16MHz_125kBPS_CFG2 = const(0xF0)
MCP_16MHz_125kBPS_CFG3 = const(0x86)

SPI_DUMMY_INT = const(0x00)
SPI_TRANSFER_LEN = const(1)
SPI_HOLD_US = const(50)

# SPI_DEFAULT_BAUDRATE = 10000000  # 10MHz
# SPI_DEFAULT_FIRSTBIT = SPI.MSB
# SPI_DEFAULT_POLARITY = 0
# SPI_DEFAULT_PHASE = 0

# Special address description flags for the CAN_ID
CAN_EFF_FLAG = const(0x80000000)  # EFF/SFF is set in the MSB
CAN_RTR_FLAG = const(0x40000000)  # remote transmission request
CAN_ERR_FLAG = const(0x20000000)  # error message frame

# Valid bits in CAN ID for frame formats
CAN_SFF_MASK = const(0x000007FF)  # standard frame format (SFF)
CAN_EFF_MASK = const(0x1FFFFFFF)  # extended frame format (EFF)
CAN_ERR_MASK = const(0x1FFFFFFF)  # omit EFF, RTR, ERR flags

# CAN_SFF_ID_BITS = const(11)
# CAN_EFF_ID_BITS = const(29)

# CAN payload length and DLC definitions according to ISO 11898-1
CAN_MAX_DLC = const(8)
CAN_MAX_DLEN = const(8)

# CAN ID length
CAN_IDLEN = const(4)

TXBnREGS = collections.namedtuple("TXBnREGS", "CTRL SIDH DATA")
RXBnREGS = collections.namedtuple("RXBnREGS", "CTRL SIDH DATA CANINTFRXnIF")

TXB = [
    TXBnREGS(REGISTER.MCP_TXB0CTRL, REGISTER.MCP_TXB0SIDH, REGISTER.MCP_TXB0DATA),
    TXBnREGS(REGISTER.MCP_TXB1CTRL, REGISTER.MCP_TXB1SIDH, REGISTER.MCP_TXB1DATA),
    TXBnREGS(REGISTER.MCP_TXB2CTRL, REGISTER.MCP_TXB2SIDH, REGISTER.MCP_TXB2DATA),
]

RXB = [
    RXBnREGS(
        REGISTER.MCP_RXB0CTRL,
        REGISTER.MCP_RXB0SIDH,
        REGISTER.MCP_RXB0DATA,
        CANINTF.CANINTF_RX0IF,
    ),
    RXBnREGS(
        REGISTER.MCP_RXB1CTRL,
        REGISTER.MCP_RXB1SIDH,
        REGISTER.MCP_RXB1DATA,
        CANINTF.CANINTF_RX1IF,
    ),
]

tsf = asyncio.ThreadSafeFlag()


class mcp2515(canio.canio):
    """a canio derived class for use with an MCP2515 CAN controller device"""

    def __init__(self, osc: int = 16_000_000, cs_pin: int = 5, interrupt_pin: int = 1, bus=None, rxq_size: int = 64,
                 txq_size: int = 8):
        super().__init__()
        self.logger = logger.logger()
        self.poll = False

        # crystal frequency
        self.osc = osc

        # message buffers
        self.rx_queue = circularQueue.circularQueue(rxq_size)
        self.tx_queue = circularQueue.circularQueue(txq_size)

        # init chip select and interrupt pins
        self.cs_pin = Pin(cs_pin, Pin.OUT)
        self.cs_pin.high()

        self.interrupt_pin = Pin(interrupt_pin, Pin.IN, Pin.PULL_UP)
        self.num_interrupts = 0

        # init SPI bus - using pin assignments for my shield designs
        if bus is None:
            self.bus = SPI(
                0,
                baudrate=10_000_000,
                polarity=0,
                phase=0,
                bits=8,
                firstbit=SPI.MSB,
                sck=Pin(2),
                mosi=Pin(3),
                miso=Pin(4),
            )
        else:
            self.bus = bus

        self.mcp2515_rx_index = 0
        self.txb_free = [True] * 3

    def spi_transfer(self, value: int = SPI_DUMMY_INT, read: bool = False):
        """Write int value to SPI and read SPI as int value simultaneously.
        This method supports transfer single byte only,
        and the system byte order doesn't matter because of that. The input and
        output int value are unsigned.
        """
        value_as_byte = value.to_bytes(SPI_TRANSFER_LEN, sys.byteorder)

        if read:
            output = bytearray(SPI_TRANSFER_LEN)
            self.bus.write_readinto(value_as_byte, output)
            return int.from_bytes(output, sys.byteorder)
        self.bus.write(value_as_byte)
        return None

    # async def process_isr(self):
    #     self.logger.log('irq handler is waiting for interrupts')
    #     while True:
    #         await tsf.wait()
    #         self.num_interrupts += 1
    #         self.poll_for_messages()

    def process_interrupts(self):
        i = self.get_interrupts()

        # if i & CANINTF.CANINTF_RX0IF:
        #     self.poll_for_messages(0)
        # elif i & CANINTF.CANINTF_RX1IF:
        #     self.poll_for_messages(1)

        if i & CANINTF.CANINTF_RX0IF or i & CANINTF.CANINTF_RX1IF:
            self.poll_for_messages()
        elif i & CANINTF.CANINTF_TX0IF:
            self.clear_txb_interrupt(0)
        elif i & CANINTF.CANINTF_TX1IF:
            self.clear_txb_interrupt(1)
        elif i & CANINTF.CANINTF_TX2IF:
            self.clear_txb_interrupt(2)

        # elif i & CANINTF.CANINTF_ERRIF:
        #     pass
        # elif i & CANINTF.CANINTF_MERRF:
        #     pass
        # else:
        #     pass

    def available(self) -> bool:
        return self.rx_queue.available()

    def get_next_message(self) -> canmessage.canmessage:
        return self.rx_queue.dequeue()

    def begin(self) -> int:
        self.reset()

        # check device is present
        self.set_register(REGISTER.MCP_CNF1, 0x55)
        tmp = self.read_register(REGISTER.MCP_CNF1)

        if tmp == 0x55:
            self.logger.log("mcp2515 device is present")
        else:
            self.logger.log("no response from mcp2515 device")
            return ERROR.ERROR_FAIL

        zeros = bytearray(14)
        self.set_registers(REGISTER.MCP_TXB0CTRL, zeros)
        self.set_registers(REGISTER.MCP_TXB1CTRL, zeros)
        self.set_registers(REGISTER.MCP_TXB2CTRL, zeros)

        self.set_register(REGISTER.MCP_RXB0CTRL, 0)
        self.set_register(REGISTER.MCP_RXB1CTRL, 0)

        # self.set_register(
        #     REGISTER.MCP_CANINTE,
        #     CANINTF.CANINTF_RX0IF
        #     | CANINTF.CANINTF_RX1IF
        #     | CANINTF.CANINTF_ERRIF
        #     | CANINTF.CANINTF_MERRF,
        # )

        # enable all interrupt sources
        # self.set_register(REGISTER.MCP_CANINTF, 0xff)

        # disable all interrupt sources
        # self.set_register(REGISTER.MCP_CANINTF, 0)

        # enable message transmit and receive interrupts
        # self.set_register(REGISTER.MCP_CANINTE,
        #                   CANINTF.CANINTF_RX0IF | CANINTF.CANINTF_RX1IF | CANINTF.CANINTF_TX0IF | CANINTF.CANINTF_TX1IF | CANINTF.CANINTF_TX2IF)

        # enable message receive interrupts
        # self.set_register(REGISTER.MCP_CANINTE, CANINTF.CANINTF_RX0IF | CANINTF.CANINTF_RX1IF)

        self.set_register(REGISTER.MCP_CANINTE, CANINTF.CANINTF_RX0IF | CANINTF.CANINTF_RX1IF |
                          CANINTF.CANINTF_TX0IF | CANINTF.CANINTF_TX1IF | CANINTF.CANINTF_TX2IF)

        # Receives all valid messages with either Standard or Extended Identifiers that
        # meet filter criteria. RXF0 is applied for RXB0, RXF1 is applied for RXB1
        self.modify_register(
            REGISTER.MCP_RXB0CTRL,
            RXBnCTRL_RXM_MASK | RXB0CTRL_BUKT | RXB0CTRL_FILHIT_MASK,
            RXBnCTRL_RXM_STDEXT | RXB0CTRL_BUKT | RXB0CTRL_FILHIT,
        )
        self.modify_register(
            REGISTER.MCP_RXB1CTRL,
            RXBnCTRL_RXM_MASK | RXB1CTRL_FILHIT_MASK,
            RXBnCTRL_RXM_STDEXT | RXB1CTRL_FILHIT,
        )

        # *** not required ***

        # Clear filters and masks
        # Do not filter any standard frames for RXF0 used by RXB0
        # Do not filter any extended frames for RXF1 used by RXB1
        # filters = (RXF.RXF0, RXF.RXF1, RXF.RXF2, RXF.RXF3, RXF.RXF4, RXF.RXF5)
        # for f in filters:
        #     ext = True if f == RXF.RXF1 else False
        #     result = self.set_filter(f, ext, 0)
        #     if result != ERROR.ERROR_OK:
        #         return result
        # masks = (MASK.MASK0, MASK.MASK1)
        # for m in masks:
        #     result = self.set_filter_mask(m, True, 0)
        #     if result != ERROR.ERROR_OK:
        #         return result

        # set bit rate - fixed at 125kb/s, using either 8 or 16 MHz crystal frequency
        self.set_bit_rate()

        # install interrupt handler and run message processor
        # self.interrupt_pin.irq(trigger=Pin.IRQ_FALLING, handler=lambda t: tsf.set())
        # self.interrupt_pin.irq(trigger=Pin.IRQ_FALLING, handler=lambda t: self.poll_for_messages())
        self.interrupt_pin.irq(trigger=Pin.IRQ_FALLING, handler=lambda t: self.process_interrupts())
        # asyncio.create_task(self.process_isr())

        # set normal mode
        self.set_normal_mode()

        return ERROR.ERROR_OK

    def reset(self):
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_RESET)
        self.cs_pin.high()
        time.sleep_ms(10)

    def read_register(self, reg: int) -> int:
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_READ)
        self.spi_transfer(reg)
        ret = self.spi_transfer(read=True)
        self.cs_pin.high()
        return ret

    def read_registers(self, reg: int, n: int) -> list:
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_READ)
        self.spi_transfer(reg)
        # MCP2515 has auto-increment of address-pointer
        values = []
        for i in range(n):
            values.append(self.spi_transfer(read=True))
        self.cs_pin.high()
        return values

    def set_register(self, reg: int, value: int) -> None:
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_WRITE)
        self.spi_transfer(reg)
        self.spi_transfer(value)
        self.cs_pin.high()

    def set_registers(self, reg: int, values: bytearray) -> None:
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_WRITE)
        self.spi_transfer(reg)
        for v in values:
            self.spi_transfer(v)
        self.cs_pin.high()

    def modify_register(self, reg: int, mask: int, data: int, spifastend: bool = False) -> None:
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_BITMOD)
        self.spi_transfer(reg)
        self.spi_transfer(mask)
        self.spi_transfer(data)
        if not spifastend:
            self.cs_pin.high()
        else:
            self.cs_pin.high()
            time.sleep_us(SPI_HOLD_US)

    def get_status(self) -> int:
        self.cs_pin.low()
        self.spi_transfer(INSTRUCTION.INSTRUCTION_READ_STATUS)
        val = self.spi_transfer(read=True)
        self.cs_pin.high()
        return val

    def set_config_mode(self) -> int:
        return self.set_mode(CANCTRL_REQOP_MODE.CANCTRL_REQOP_CONFIG)

    # def set_listen_only_mode(self) -> int:
    #     return self.set_mode(CANCTRL_REQOP_MODE.CANCTRL_REQOP_LISTENONLY)
    #
    # def set_sleep_mode(self) -> int:
    #     return self.set_mode(CANCTRL_REQOP_MODE.CANCTRL_REQOP_SLEEP)
    #
    # def set_loopback_mode(self) -> int:
    #     return self.set_mode(CANCTRL_REQOP_MODE.CANCTRL_REQOP_LOOPBACK)

    def set_normal_mode(self) -> int:
        return self.set_mode(CANCTRL_REQOP_MODE.CANCTRL_REQOP_NORMAL)

    def set_mode(self, mode: int) -> int:
        self.modify_register(REGISTER.MCP_CANCTRL, CANCTRL_REQOP, mode)

        end_time = time.ticks_add(time.ticks_ms(), 10)
        mode_match = False
        while time.ticks_diff(time.ticks_ms(), end_time) < 0:
            newmode = self.read_register(REGISTER.MCP_CANSTAT)
            newmode &= CANSTAT_OPMOD

            mode_match = newmode == mode
            if mode_match:
                break

        return ERROR.ERROR_OK if mode_match else ERROR.ERROR_FAIL

    def set_bit_rate(self) -> int:
        error = self.set_config_mode()
        if error != ERROR.ERROR_OK:
            return error

        # fixed to 125kbs with 8 or 16 MHz crystal

        if self.osc == 16_000_000:
            cfg1 = MCP_16MHz_125kBPS_CFG1
            cfg2 = MCP_16MHz_125kBPS_CFG2
            cfg3 = MCP_16MHz_125kBPS_CFG3
        elif self.osc == 8_000_000:
            cfg1 = MCP_8MHz_125kBPS_CFG1
            cfg2 = MCP_8MHz_125kBPS_CFG2
            cfg3 = MCP_8MHz_125kBPS_CFG3
        else:
            raise ValueError('Unsupported oscillator frequency')

        self.set_register(REGISTER.MCP_CNF1, cfg1)
        self.set_register(REGISTER.MCP_CNF2, cfg2)
        self.set_register(REGISTER.MCP_CNF3, cfg3)
        return ERROR.ERROR_OK

    # def set_CLKOUT(self, divisor: int) -> int:
    #     if divisor == CAN_CLKOUT.CLKOUT_DISABLE:
    #         # Turn off CLKEN
    #         self.modify_register(REGISTER.MCP_CANCTRL, CANCTRL_CLKEN, 0x00)
    #
    #         # Turn on CLKOUT for SOF
    #         self.modify_register(REGISTER.MCP_CNF3, CNF3_SOF, CNF3_SOF)
    #         return ERROR.ERROR_OK
    #
    #     # Set the prescaler (CLKPRE)
    #     self.modify_register(REGISTER.MCP_CANCTRL, CANCTRL_CLKPRE, divisor)
    #
    #     # Turn on CLKEN
    #     self.modify_register(REGISTER.MCP_CANCTRL, CANCTRL_CLKEN, CANCTRL_CLKEN)
    #
    #     # Turn off CLKOUT for SOF
    #     self.modify_register(REGISTER.MCP_CNF3, CNF3_SOF, 0x00)
    #
    #     return ERROR.ERROR_OK

    def prepare_id(self, ext: bool, id_: int) -> bytearray:
        canid = id_ & 0xffff
        buffer = bytearray(CAN_IDLEN)

        if ext:
            buffer[MCP_EID0] = canid & 0xff
            buffer[MCP_EID8] = canid >> 8
            canid = id_ >> 16
            buffer[MCP_SIDL] = canid & 0x03
            buffer[MCP_SIDL] += (canid & 0x1C) << 3
            buffer[MCP_SIDL] |= TXB_EXIDE_MASK
            buffer[MCP_SIDH] = canid >> 5
        else:
            buffer[MCP_SIDH] = canid >> 3
            buffer[MCP_SIDL] = (canid & 0x07) << 5
            buffer[MCP_EID0] = 0
            buffer[MCP_EID8] = 0

        return buffer

    # def set_filter_mask(self, mask: int, ext: int, ulData: int) -> int:
    #     res = self.set_config_mode()
    #     if res != ERROR.ERROR_OK:
    #         return res
    #
    #     reg = None
    #     if mask == MASK.MASK0:
    #         reg = REGISTER.MCP_RXM0SIDH
    #     elif mask == MASK.MASK1:
    #         reg = REGISTER.MCP_RXM1SIDH
    #     else:
    #         return ERROR.ERROR_FAIL
    #
    #     tbufdata = self.prepare_id(ext, ulData)
    #     self.set_registers(reg, tbufdata)
    #
    #     return ERROR.ERROR_OK
    #
    # def set_filter(self, ft: int, ext: int, ulData: int) -> int:
    #     res = self.set_config_mode()
    #     if res != ERROR.ERROR_OK:
    #         return res
    #
    #     reg = None
    #     if ft == RXF.RXF0:
    #         reg = REGISTER.MCP_RXF0SIDH
    #     elif ft == RXF.RXF1:
    #         reg = REGISTER.MCP_RXF1SIDH
    #     elif ft == RXF.RXF2:
    #         reg = REGISTER.MCP_RXF2SIDH
    #     elif ft == RXF.RXF3:
    #         reg = REGISTER.MCP_RXF3SIDH
    #     elif ft == RXF.RXF4:
    #         reg = REGISTER.MCP_RXF4SIDH
    #     elif ft == RXF.RXF5:
    #         reg = REGISTER.MCP_RXF5SIDH
    #     else:
    #         return ERROR.ERROR_FAIL
    #
    #     tbufdata = self.prepare_id(ext, ulData)
    #     self.set_registers(reg, tbufdata)
    #
    #     return ERROR.ERROR_OK

    # def process_txb_interrupt(self) -> None:
    #     if self.tx_queue.available():
    #         self.send_message_(self.tx_queue.dequeue())
    #
    # def process_rxb_interrupt(self):
    #     err, msg = self.read_message_()
    #     if err == ERROR.ERROR_OK:
    #         return msg
    #     else:
    #         return None

    def send_message(self, msg: canmessage.canmessage, txbn=None) -> int:
        if self.txb_free[0] or self.txb_free[1] or self.txb_free[2]:
            return self.send_message_(msg, txbn)
        else:
            self.tx_queue.enqueue(msg)
            return ERROR.ERROR_OK

    def send_message_(self, frame: canmessage.canmessage, txbn=None) -> int:
        if txbn is None:
            return self.send_message__(frame)

        if frame.dlc > CAN_MAX_DLEN:
            return ERROR.ERROR_FAILTX

        txbuf = TXB[txbn]
        id_ = frame.canid & (CAN_EFF_MASK if frame.ext else CAN_SFF_MASK)

        if frame.rtr:
            id_ |= CAN_RTR_FLAG

        data = self.prepare_id(frame.ext, id_)
        mcp_dlc = (frame.dlc | RTR_MASK) if frame.rtr else frame.dlc

        data.extend(bytearray(1 + frame.dlc))
        data[MCP_DLC] = mcp_dlc
        data[MCP_DATA: MCP_DATA + frame.dlc] = frame.data

        self.set_registers(txbuf.SIDH, data)

        self.modify_register(
            txbuf.CTRL, TXBnCTRL.TXB_TXREQ, TXBnCTRL.TXB_TXREQ, spifastend=True
        )

        ctrl = self.read_register(txbuf.CTRL)
        if ctrl & (TXBnCTRL.TXB_ABTF | TXBnCTRL.TXB_MLOA | TXBnCTRL.TXB_TXERR):
            return ERROR.ERROR_FAILTX

        return ERROR.ERROR_OK

    def send_message__(self, frame: canmessage.canmessage) -> int:
        if frame.dlc > CAN_MAX_DLEN:
            return ERROR.ERROR_FAILTX

        tx_buffers = (TXBn.TXB0, TXBn.TXB1, TXBn.TXB2)

        for i in range(N_TXBUFFERS):
            txbuf = TXB[tx_buffers[i]]
            ctrlval = self.read_register(txbuf.CTRL)
            if (ctrlval & TXBnCTRL.TXB_TXREQ) == 0:
                return self.send_message_(frame, tx_buffers[i])

        return ERROR.ERROR_ALLTXBUSY

    def read_message(self, rxbn: int = None) -> tuple:
        if rxbn is None:
            return self.read_message_()

        rxb = RXB[rxbn]
        tbufdata = self.read_registers(rxb.SIDH, 1 + CAN_IDLEN)

        id_ = (tbufdata[MCP_SIDH] << 3) + (tbufdata[MCP_SIDL] >> 5)

        if (tbufdata[MCP_SIDL] & TXB_EXIDE_MASK) == TXB_EXIDE_MASK:
            id_ = (id_ << 2) + (tbufdata[MCP_SIDL] & 0x03)
            id_ = (id_ << 8) + tbufdata[MCP_EID8]
            id_ = (id_ << 8) + tbufdata[MCP_EID0]
            id_ |= CAN_EFF_FLAG

        dlc_ = tbufdata[MCP_DLC] & DLC_MASK
        if dlc_ > CAN_MAX_DLEN:
            return ERROR.ERROR_FAIL, None

        ctrl = self.read_register(rxb.CTRL)
        if ctrl & RXBnCTRL_RTR:
            id_ |= CAN_RTR_FLAG

        frame = canmessage.canmessage(canid=id_, dlc=dlc_)
        frame.data = bytearray(self.read_registers(rxb.DATA, dlc_))

        return ERROR.ERROR_OK, frame

    def read_message_(self):
        rc = ERROR.ERROR_NOMSG, None

        stat = self.get_status()
        if stat & STAT.STAT_RX0IF and self.mcp2515_rx_index == 0:
            rc = self.read_message(RXBn.RXB0)
            if self.get_status() & STAT.STAT_RX1IF:
                self.mcp2515_rx_index = 1
            self.modify_register(REGISTER.MCP_CANINTF, RXB[RXBn.RXB0].CANINTFRXnIF, 0)
        elif stat & STAT.STAT_RX1IF:
            rc = self.read_message(RXBn.RXB1)
            self.mcp2515_rx_index = 0
            self.modify_register(REGISTER.MCP_CANINTF, RXB[RXBn.RXB1].CANINTFRXnIF, 0)

        return rc

    def poll_for_messages(self, rxbn: int = None):
        while self.check_receive():
            # self.logger.log('mcp2515 has message')
            # us = time.ticks_us()
            self.num_interrupts += 1
            r, msg = self.read_message(rxbn)
            if r == ERROR.ERROR_OK:
                self.rx_queue.enqueue(msg)
                # self.logger.log(f'message processing took {time.ticks_diff(time.ticks_us(), us)} us')
                # self.logger.log('message queued')
            else:
                self.logger.log(f'mcp2515: no message, err = {r}')

    def check_receive(self) -> bool:
        res = self.get_status()
        if res & STAT_RXIF_MASK:
            return True
        return False

    def check_error(self) -> bool:
        eflg = self.check_error_flags()

        if eflg & EFLG_ERRORMASK:
            return True
        return False

    def check_error_flags(self) -> int:
        return self.read_register(REGISTER.MCP_EFLG)

    def receive_error_count(self):
        return self.read_register(REGISTER.MCP_REC)

    def transmit_error_count(self):
        return self.read_register(REGISTER.MCP_TEC)

    def get_interrupts(self) -> int:
        return self.read_register(REGISTER.MCP_CANINTF)

    def clear_txb_interrupt(self, txb_num: int):
        # self.logger.log(f'clear_txb_interrupt: txb{txb_num} is now free')
        self.txb_free[txb_num] = True

        if txb_num == 0:
            reg = CANINTF.CANINTF_TX0IF
        elif txb_num == 1:
            reg = CANINTF.CANINTF_TX1IF
        else:
            reg = CANINTF.CANINTF_TX2IF

        self.modify_register(REGISTER.MCP_CANINTF, reg, 0)

# def clear_RXnOVR_flags(self) -> None:
#     self.modify_register(REGISTER.MCP_EFLG, EFLG.EFLG_RX0OVR | EFLG.EFLG_RX1OVR, 0)

# def clear_interrupts(self) -> None:
#     self.set_register(REGISTER.MCP_CANINTF, 0)
#
# def get_interrupt_mask(self) -> int:
#     return self.read_register(REGISTER.MCP_CANINTE)
#
# def clear_TX_interrupts(self) -> None:
#     self.modify_register(
#         REGISTER.MCP_CANINTF,
#         CANINTF.CANINTF_TX0IF | CANINTF.CANINTF_TX1IF | CANINTF.CANINTF_TX2IF,
#         0,
#     )
#
# def clear_RXnOVR(self) -> None:
#     eflg = self.check_error_flags()
#     if eflg != 0:
#         self.clear_RXnOVR_flags()
#         self.clear_interrupts()
#         # modify_register(REGISTER.MCP_CANINTF, CANINTF.CANINTF_ERRIF, 0)
#
# def clear_MERR(self) -> None:
#     # self.modify_register(REGISTER.MCP_EFLG, EFLG.EFLG_RX0OVR | EFLG.EFLG_RX1OVR, 0)
#     # self.clear_interrupts()
#     self.modify_register(REGISTER.MCP_CANINTF, CANINTF.CANINTF_MERRF, 0)
#
# def clear_ERRIF(self) -> None:
#     # self.modify_register(REGISTER.MCP_EFLG, EFLG.EFLG_RX0OVR | EFLG.EFLG_RX1OVR, 0)
#     # self.clear_interrupts()
#     self.modify_register(REGISTER.MCP_CANINTF, CANINTF.CANINTF_ERRIF, 0)
