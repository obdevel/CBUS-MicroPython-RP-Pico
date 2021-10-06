import machine
import circularQueue
import time

_RESET_COMMAND = 0xC0
_WRITE_COMMAND = 0x02
_READ_COMMAND = 0x03
_BIT_MODIFY_COMMAND = 0x05
_LOAD_TX_BUFFER_COMMAND = 0x40
_REQUEST_TO_SEND_COMMAND = 0x80
_READ_FROM_RXB0SIDH_COMMAND = 0x90
_READ_FROM_RXB1SIDH_COMMAND = 0x94
_READ_STATUS_COMMAND = 0xA0
_RX_STATUS_COMMAND = 0xB0

_BFPCTRL_REGISTER = 0x0C
_TXRTSCTRL_REGISTER = 0x0D
_CANSTAT_REGISTER = 0x0E
_CANCTRL_REGISTER = 0x0F
_TEC_REGISTER = 0x1C
_REC_REGISTER = 0x1D
_RXM0SIDH_REGISTER = 0x20
_RXM1SIDH_REGISTER = 0x24
_CNF3_REGISTER = 0x28
_CNF2_REGISTER = 0x29
_CNF1_REGISTER = 0x2A
_CANINTF_REGISTER = 0x2C
_EFLG_REGISTER = 0x2D
_TXB0CTRL_REGISTER = 0x30
_TXB1CTRL_REGISTER = 0x40
_TXB2CTRL_REGISTER = 0x50
_RXB0CTRL_REGISTER = 0x60
_RXB1CTRL_REGISTER = 0x70

RXFSIDH_REGISTER = {0x00, 0x04, 0x08, 0x10, 0x14, 0x18}


class mcp2515():

    """ a class to interface to a MCP2515 CAN controller device """

    def __init__(self, cs_pin=5, int_pin=1, spi=None):
        # set variables
        print('MCP2515 constructor begins')
        self._spi = spi
        self._inbuff = bytearray(1)
        self._mTXBIsFree = [True, True, True]

        # create buffers
        self.rx_queue = circularQueue.circularQueue(64)
        self.tx_queue = circularQueue.circularQueue(64)

        # init CS and interrupt pins
        self._cs_pin = machine.Pin(cs_pin, machine.Pin.OUT)
        self._cs_pin.on()

        self._int_pin = machine.Pin(int_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self._int_pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=self.isr)

        # init SPI bus
        self._spi = machine.SPI(0,
            baudrate=10_000_000, polarity=0, phase=0, bits=8,
            sck=machine.Pin(2),
            mosi=machine.Pin(3), miso=machine.Pin(4))

        print('MCP2515 constructor complete')

    def isr():
        # interrupt handler
        print('MCP2515 ISR triggered')

    def select(self, state):
        if state:
            # machine.disable_irq()
            self._cs_pin.off()
        else:
            self._cs_pin.on()
            # machine.enable_irq()

    def write_register(self, register, value):
        # write a value to a MCP2515 register over SPI and return the response
        self.select(True)
        self._spi.write_readinto(_WRITE_COMMAND, self._inbuff)
        self.select(False)
        return self._inbuff

    def setupMaskRegister(self, in_mask, in_reg):
        pass

    def begin(self):
        # reset MCP2515
        print('device reset')
        self.select(True)
        self._spi.write(bytearray(_RESET_COMMAND))
        self.select(False)
        time.sleep_us(10)

        # check device is accessible
        print('check device is accessible')
        self.select(True)
        ok = False
        self._spi.write(_CNF1_REGISTER, 0x55)
        ok = self._spi.read(_CNF1_REGISTER) == 0x55

        if ok:
            self._spi.write(_CNF2_REGISTER, 0xAA)
            ok = self._spi.read(_CNF2_REGISTER) == 0xAA

        self.select(False)

        if not ok:
            print('check failed')
            return False

        # initial device config
        print('proceed with device config')

        # CNF3, 2, 1
        # 125000: (0x03, 0xF0, 0x86),

        #define MCP_16MHz_125kBPS_CFG1 (0x43)     /* Increased SJW       */
        #define MCP_16MHz_125kBPS_CFG2 (0xE5)
        #define MCP_16MHz_125kBPS_CFG3 (0x83)     /* Sample point at 75% */

        #define MCP_8MHz_125kBPS_CFG1 (0x81)   /* Increased SJW       */
        #define MCP_8MHz_125kBPS_CFG2 (0xE5)   /* Enabled SAM bit     */
        #define MCP_8MHz_125kBPS_CFG3 (0x83)   /* Sample point at 75% */

        print('set baud rate')
        self._spi.write(_WRITE_COMMAND)
        self._spi.write(_CNF3_REGISTER)
        self._spi.write(0x86)
        self._spi.write(0xF0)
        self._spi.write(0x03)

        # CANINTE interrupts register
        print('set interrupts')
        self._spi.write(0x1F)

        self.select(False)

        # misc
        self.write_register(_BFPCTRL_REGISTER, 0)
        self.write_register(_TXRTSCTRL_REGISTER, 0)
        self.write_register(__RXB0CTRL_REGISTER, 0)
        self.write_register(__RXB1CTRL_REGISTER, 0)

    def available(self):
        return self.rx_queue.available()
