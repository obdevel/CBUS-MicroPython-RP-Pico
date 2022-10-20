# mcp2515.py

import machine
import circularQueue
import time
import canio
import canmessage

# speed 8M
MCP_8MHz_125kBPS_CFG1 = 0x81
MCP_8MHz_125kBPS_CFG2 = 0xE5
MCP_8MHz_125kBPS_CFG3 = 0x83

# speed 16M
MCP_16MHz_125kBPS_CFG1 = 0x43
MCP_16MHz_125kBPS_CFG2 = 0xE5
MCP_16MHz_125kBPS_CFG3 = 0x83

# commands
RESET_COMMAND = 0xC0
WRITE_COMMAND = 0x02
READ_COMMAND = 0x03
BIT_MODIFY_COMMAND = 0x05
LOAD_TX_BUFFER_COMMAND = 0x40
REQUEST_TO_SEND_COMMAND = 0x80
READ_FROM_RXB0SIDH_COMMAND = 0x90
READ_FROM_RXB1SIDH_COMMAND = 0x94
READ_STATUS_COMMAND = 0xA0
RX_STATUS_COMMAND = 0xB0

# registers
BFPCTRL_REGISTER = 0x0C
TXRTSCTRL_REGISTER = 0x0D
CANSTAT_REGISTER = 0x0E
CANCTRL_REGISTER = 0x0F
TEC_REGISTER = 0x1C
REC_REGISTER = 0x1D
RXM0SIDH_REGISTER = 0x20
RXM1SIDH_REGISTER = 0x24
CNF3_REGISTER = 0x28
CNF2_REGISTER = 0x29
CNF1_REGISTER = 0x2A
CANINTE_REGISTER = 0x2B
CANINTF_REGISTER = 0x2C
EFLG_REGISTER = 0x2D
TXB0CTRL_REGISTER = 0x30
TXB1CTRL_REGISTER = 0x40
TXB2CTRL_REGISTER = 0x50
RXB0CTRL_REGISTER = 0x60
RXB1CTRL_REGISTER = 0x70
RXFSIDH_REGISTER = [0x00, 0x04, 0x08, 0x10, 0x14, 0x18]


class mcp2515(canio.canio):

    """a canio derived class for use with an MCP2515 CAN controller device"""

    def __init__(self, osc=16000000, cs_pin=5, int_pin=1, bus=None, qsize=64):
        print("** mcp2515 constructor")

        # call superclass constructor
        super().__init__()

        # crystal frequency
        self.osc = osc

        # create message buffers
        self.rx_queue = circularQueue.circularQueue(qsize)
        self.tx_queue = circularQueue.circularQueue(qsize)

        # init chip select and interrupt pins
        self.cs_pin = machine.Pin(cs_pin, machine.Pin.OUT)
        self.cs_pin.on()

        self.int_pin = machine.Pin(int_pin, machine.Pin.IN, machine.Pin.PULL_UP)

        # init SPI bus
        if bus is None:
            self.bus = machine.SPI(
                0,
                baudrate=10_000_000,
                polarity=0,
                phase=0,
                bits=8,
                firstbit=machine.SPI.MSB,
                sck=machine.Pin(2),
                mosi=machine.Pin(3),
                miso=machine.Pin(4),
            )
        else:
            self.bus = bus

    def isr(self, source=None):
        # CAN interrupt handler
        print(f"** mcp2515 isr triggered, source = {source}")

        handled = False

        self.chip_select(True)
        ret = self.read_register(CANSTAT_REGISTER)
        print(f"ret = {ret}")
        intr_type = int(ret[0]) & 0x0E

        print(f"state = {intr_type}")

        while intr_type != 0:
            handled = True

            if intr_type == (1 << 1):  # error interrupt
                self.modify_register(CANINTF_REGISTER, 0x20, 0)
            elif intr_type == (2 << 1):  # wakeup interrupt
                self.modify_register(CANINTF_REGISTER, 0x40, 0)
            elif intr_type == (3 << 1):  # TXB0 interrupt
                self.handle_txb_interrupt(0)
            elif intr_type == (4 << 1):  # TXB1 interrupt
                self.handle_txb_interrupt(1)
            elif intr_type == (5 << 1):  # TXB2 interrupt
                self.handle_txb_interrupt(2)
            elif intr_type == (6 << 1) or intr_type == (7 << 1):  # RXB interrupts
                self.handle_rxb_interrupt()

            ret = self.read_register(CANSTAT_REGISTER)
            intr_type = int(ret[0]) & 0x0E
            print(f"interrupt = {intr_type}")

        self.chip_select(False)
        print("** end of isr")

        return handled

    def chip_select(self, state):
        if state:
            # machine.disable_irq()
            # print("CS low")
            # self.cs_pin.off()
            self.cs_pin.value(0)
        else:
            # print("CS high")
            # self.cs_pin.on()
            self.cs_pin.value(1)
            # machine.enable_irq()

    def read_register(self, reg):
        # print(f'read_register {reg}')

        msg = bytearray()
        msg.append(READ_COMMAND)
        msg.append(reg)

        self.chip_select(True)
        self.bus.write(msg)
        ret = self.bus.read(1)
        self.chip_select(False)

        return ret

    def read_registers(self, reg, values, n):
        # print('read_registers')

        msg = bytearray()
        msg.append(READ_COMMAND)
        msg.append(reg)

        self.chip_select(True)
        self.bus.write(msg)
        value = self.bus.read(n)
        self.chip_select(False)

    def write_register(self, reg, value):
        # print(f'write_register {reg}')

        msg = bytearray()
        msg.append(WRITE_COMMAND)
        msg.append(reg)
        msg.append(value)

        self.chip_select(True)
        self.bus.write(msg)
        self.chip_select(False)

    def write_registers(self, reg, values):
        # print('write_registers')

        msg = bytearray()
        msg.append(WRITE_COMMAND)
        msg.append(reg)

        for b in values:
            msg.append(b)

        self.chip_select(True)
        self.bus.write(msg)
        self.chip_select(False)

    def modify_register(self, reg, mask, data):
        # print('modify_register')

        msg = bytearray()
        msg.append(BIT_MODIFY_COMMAND)
        msg.append(reg)
        msg.append(mask)
        msg.append(data)

        self.chip_select(True)
        self.bus.write(msg)
        self.chip_select(False)

    def read_rx_status(self):
        # print('read_rx_status')
        reg = bytearray(RX_STATUS_COMMAND)
        self.chip_select(True)
        self.bus.write(reg)
        read = self.bus.read(1, 0)
        self.chip_select(False)

        return read[0]

    def handle_rxb_interrupt(self):
        print("handle_rxb_interrupt")

        got_msg = False
        rx_status = self.read_rx_status()

        if rx_status & 0xC0:
            print("new message available")
            got_msg = True
            message = canmessage.canmessage()
            access_rxb0 = (rx_status & 0x40) != 0
            message.rtr = (rx_status & 0x08) != 0
            message.ext = (rx_status & 0x10) != 0

            if access_rxb0:
                print("from RXB0")
                reg = READ_FROM_RXB0SIDH_COMMAND
            else:
                print("from RXB1")
                reg = READ_FROM_RXB1SIDH_COMMAND

            self.chip_select(True)

            v = bytearray()
            v.append(reg)
            self.bus.write(v)
            message.id = self.bus.read(1)[0]
            sidl = self.bus.read(1)
            message.id <<= 3
            message.id |= sidl >> 5
            eid8 = self.bus.read(1)

            if message.ext:
                message.id <<= 2
                message.id |= sidl & 0x03
                message.id <<= 8
                message.id |= eid8

            eid0 = self.bus.read(1)[0]

            if message.ext:
                message.id <<= 8
                message.id |= eid0

            dlc = self.bus.read(1)[0]
            message.len = dlc & 0x0F
            message.data = self.bus.read(msg.len)

            self.chip_select(False)
            self.rx_queue.enqueue(message)

        else:
            print("no message available")

    def handle_txb_interrupt(self, txb):
        print("handle_txb_interrupt")

        self.modify_register(CANINTF_REGISTER, (0x04 << txb), 0)

        if self.tx_queue.available():
            print("sending queued msg")
            msg = self.tx_queue.dequeue()
            self.internal_send_message(msg, txb)
        else:
            print("no queued msg to tx")
            self.txb_is_free[txb] = True

    def internal_send_message(self, msg, txb):
        print(
            f"internal_send_message using txb = {txb}, id = {msg.id:#x}, len = {msg.len}"
        )

        self.chip_select(True)

        load_tx_buffer_command = bytearray(LOAD_TX_BUFFER_COMMAND | (txb << 1))
        self.bus.write(load_tx_buffer_command)

        if msg.ext:
            print("extended message")
            v = msg.id >> 21
            self.bus.write(bytearray(v))
            v = (msg.id >> 13) & 0xE0
            v |= (msg.id >> 16) & 0x03
            v |= 0x08
            self.bus.write(bytearray(v))
            v = (msg.id >> 8) & 0xFF
            self.bus.write(bytearray(v))
            v = msg.id & 0xFF
        else:
            print("standard message")
            v = msg.id >> 3
            self.bus.write(bytearray(v))
            v = (msg.id << 5) & 0xE0
            self.bus.write(bytearray(v))
            self.bus.write(bytearray(0))
            self.bus.write(bytearray(0))

        v = msg.len

        if msg.rtr:
            print("rtr message")
            v |= 0x40

        self.bus.write(bytearray(v))

        if not msg.rtr:
            self.bus.write(bytearray(msg.data))

        self.chip_select(False)

        self.chip_select(True)
        send_command = REQUEST_TO_SEND_COMMAND | (1 << txb)
        self.bus.write(bytearray(send_command))
        self.chip_select(False)

        print("internal_send_message ends")

    def reset(self):
        print("** mcp2515 reset")
        msg = bytearray()
        msg.append(RESET_COMMAND)
        self.chip_select(True)
        self.bus.write(msg)
        self.chip_select(False)
        time.sleep_ms(5)

    def begin(self):
        print("** mcp2515 begin")
        self.reset()

        # check device is present
        self.write_register(CNF1_REGISTER, 0x55)
        x = self.read_register(CNF1_REGISTER)

        if x[0] == 0x55:
            print("** mcp2515 device is present")
        else:
            print("no response from mcp2515 device")

        # init tx buffer states
        self.txb_is_free = [True, True, True]

        # set CNF registers for bus speed
        # print(f'oscillator freq = {self.osc}')

        if self.osc == 16000000:
            self.write_register(CNF1_REGISTER, MCP_16MHz_125kBPS_CFG1)
            self.write_register(CNF2_REGISTER, MCP_16MHz_125kBPS_CFG2)
            self.write_register(CNF3_REGISTER, MCP_16MHz_125kBPS_CFG3)
        elif self.osc == 8000000:
            self.write_register(CNF1_REGISTER, MCP_8MHz_125kBPS_CFG1)
            self.write_register(CNF2_REGISTER, MCP_8MHz_125kBPS_CFG2)
            self.write_register(CNF3_REGISTER, MCP_8MHz_125kBPS_CFG3)
        else:
            print("*** error: unsupported oscillator frequency")

        # configure interrupts
        self.write_register(CANINTE_REGISTER, 0x1F)

        # configure i/o pins
        self.write_register(BFPCTRL_REGISTER, 0)
        self.write_register(TXRTSCTRL_REGISTER, 0)

        # configure receive buffer rollover
        self.write_register(RXB0CTRL_REGISTER, 1 << 2)
        self.write_register(RXB1CTRL_REGISTER, 0)

        # configure mask registers - no filters or masks set
        values = bytearray()
        values.append(0)
        values.append(0)
        values.append(0)
        values.append(0)
        self.write_registers(RXM0SIDH_REGISTER, values)

        values = bytearray()
        values.append(0)
        values.append(0)
        values.append(0)
        values.append(0)
        self.write_registers(RXM0SIDH_REGISTER, values)

        # configure transmit buffer priority
        self.write_register(TXB0CTRL_REGISTER, 0)
        self.write_register(TXB1CTRL_REGISTER, 0)
        self.write_register(TXB2CTRL_REGISTER, 0)

        # init transmit buffer states
        self.txb_is_free = [True, True, True]

        # set mode
        self.write_register(CANCTRL_REGISTER, 0)
        time.sleep_ms(5)
        x = self.read_register(CANCTRL_REGISTER)

        if x[0] != 0:
            print("error waiting for mode change")

        # install ISR
        self.int_pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=self.isr)

        print("** mcp2515 init complete")

    def available(self):
        # print('** available')
        return self.rx_queue.available()

    def send_message(self, msg):
        print("** send_message")
        msg.make_header()

        txb = 0

        if self.txb_is_free[txb]:
            print("device buffer is free, sending message immediately")
            self.internal_send_message(msg, txb)
            self.txb_is_free[txb] = False
            ret = True
        else:
            print("device buffer is full, queueing message for later")

            if self.tx_queue.enqueue(msg):
                print("message queued ok")
                ret = True
            else:
                print("queue is full")
                ret = False

        print("** send message ends")
        return ret

    def get_next_message(self):
        # print('** get_next_message')

        if self.available():
            # machine.disable_irq()
            msg = self.rx_queue.dequeue()
            # machine.enable_irq()
            return msg
        else:
            return None
