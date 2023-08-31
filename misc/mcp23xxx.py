from machine import I2C, Pin
from micropython import const

MCP23017_ADDRESS = const(0x20)  # !< MCP23017 Address

# registers
MCP23017_IODIRA = const(0x00)  # !< I/O direction register A
MCP23017_IPOLA = const(0x02)  # !< Input polarity port register A
MCP23017_GPINTENA = const(0x04)  # !< Interrupt-on-change pins A
MCP23017_DEFVALA = const(0x06)  # !< Default value register A
MCP23017_INTCONA = const(0x08)  # !< Interrupt-on-change control register A
MCP23017_IOCONA = const(0x0A)  # !< I/O expander configuration register A
MCP23017_GPPUA = const(0x0C)  # !< GPIO pull-up resistor register A
MCP23017_INTFA = const(0x0E)  # !< Interrupt flag register A
MCP23017_INTCAPA = const(0x10)  # !< Interrupt captured value for port register A
MCP23017_GPIOA = const(0x12)  # !< General purpose I/O port register A
MCP23017_OLATA = const(0x14)  # !< Output latch register 0 A

MCP23017_IODIRB = const(0x01)  # !< I/O direction register B
MCP23017_IPOLB = const(0x03)  # !< Input polarity port register B
MCP23017_GPINTENB = const(0x05)  # !< Interrupt-on-change pins B
MCP23017_DEFVALB = const(0x07)  # !< Default value register B
MCP23017_INTCONB = const(0x09)  # !< Interrupt-on-change control register B
MCP23017_IOCONB = const(0x0B)  # !< I/O expander configuration register B
MCP23017_GPPUB = const(0x0D)  # !< GPIO pull-up resistor register B
MCP23017_INTFB = const(0x0F)  # !< Interrupt flag register B
MCP23017_INTCAPB = const(0x11)  # !< Interrupt captured value for port register B
MCP23017_GPIOB = const(0x13)  # !< General purpose I/O port register B
MCP23017_OLATB = const(0x15)  # !< Output latch register 0 B

MCP23017_INT_ERR = const(255)  # !< Interrupt error

INPUT = const(0)
OUTPUT = const(1)

LOW = const(0)
HIGH = const(1)
CHANGE = const(2)
FALLING = const(3)


class mcp23017:
    def __init__(self, bus=None, addr: int = MCP23017_ADDRESS, scl_pin: int = 0, sda_pin: int = 0) -> None:
        self.bus = bus
        self.addr = addr
        self.scl_pin = scl_pin
        self.sda_pin = sda_pin

    def begin(self) -> None:
        if self.bus is None:
            self.bus = I2C(0, scl=Pin(self.scl_pin), sda=Pin(self.sda_pin), freq=400_000)

        self.write_register(MCP23017_IODIRA, 0xff)
        self.write_register(MCP23017_IODIRB, 0xff)

        self.write_register(MCP23017_GPINTENA, 0x00)
        self.write_register(MCP23017_GPINTENB, 0x00)

        self.write_register(MCP23017_GPPUA, 0x00)
        self.write_register(MCP23017_GPPUB, 0x00)

    def pin_mode(self, pin: int, mode: int) -> None:
        self.update_register_bit(pin, (mode == INPUT), MCP23017_IODIRA, MCP23017_IODIRB)

    def pullup(self, pin: int, val: int) -> None:
        self.update_register_bit(pin, val, MCP23017_GPPUA, MCP23017_GPPUB)

    def digital_write(self, pin: int, val: int) -> None:
        bit = self.bit_for_pin(pin)

        reg = self.reg_for_pin(pin, MCP23017_OLATA, MCP23017_OLATB)
        gpio = self.read_register(reg)
        self.bit_write(gpio, bit, val)

        reg = self.reg_for_pin(pin, MCP23017_GPIOA, MCP23017_GPIOB)
        self.write_register(reg, gpio)

    def digital_read(self, pin: int) -> int:
        bit = self.bit_for_pin(pin)
        reg = self.reg_for_pin(pin, MCP23017_GPIOA, MCP23017_GPIOB)
        return (self.read_register(reg) >> bit) & 0x1

    def set_interrupts(self, mirroring, open_drain, polarity) -> None:
        ioconf_value = self.read_register(MCP23017_IOCONA)
        self.bit_write(ioconf_value, 6, mirroring)
        self.bit_write(ioconf_value, 2, open_drain)
        self.bit_write(ioconf_value, 1, polarity)
        self.write_register(MCP23017_IOCONA, ioconf_value)

        ioconf_value = self.read_register(MCP23017_IOCONB)
        self.bit_write(ioconf_value, 6, mirroring)
        self.bit_write(ioconf_value, 2, open_drain)
        self.bit_write(ioconf_value, 1, polarity)
        self.write_register(MCP23017_IOCONB, ioconf_value)

    def set_interrupt_pin(self, pin: int, mode: int) -> None:
        self.update_register_bit(pin, (mode != CHANGE), MCP23017_INTCONA, MCP23017_INTCONB)
        self.update_register_bit(pin, (mode == FALLING), MCP23017_DEFVALA, MCP23017_DEFVALB)
        self.update_register_bit(pin, HIGH, MCP23017_GPINTENA, MCP23017_GPINTENB)

    def disable_interrupt_pin(self, pin: int) -> None:
        self.update_register_bit(pin, LOW, MCP23017_GPINTENA, MCP23017_GPINTENB)

    def get_last_interrupt_pin(self) -> int:
        intf = self.read_register(MCP23017_INTFA)
        for i in range(8):
            if self.bit_read(intf, i):
                return i

        intf = self.read_register(MCP23017_INTFB)
        for i in range(8):
            if self.bit_read(intf, i):
                return i + 8

        return MCP23017_INT_ERR

    def get_last_interrupt_pin_value(self) -> int:
        int_pin = self.get_last_interrupt_pin()

        if int_pin != MCP23017_INT_ERR:
            int_cap_reg = self.reg_for_pin(int_pin, MCP23017_INTCAPA, MCP23017_INTCAPB)
            bit = self.bit_for_pin(int_pin)
            return (self.read_register(int_cap_reg) >> bit) & 0x01

        return MCP23017_INT_ERR

    # private API

    def read_register(self, reg) -> int:
        return 0

    def write_register(self, reg, val) -> None:
        pass

    def update_register_bit(self, pin, val, port_a_addr, post_b_addr):
        pass

    def read_gpio_AB(self) -> int:
        return 0

    def read_gpio(self, port) -> int:
        return 0

    def write_gpio_AB(self, val):
        pass

    @staticmethod
    def bit_for_pin(pin) -> int:
        return pin % 8

    @staticmethod
    def reg_for_pin(pin, port_a_reg, port_b_reg) -> int:
        return port_a_reg if pin < 8 else port_b_reg

    @staticmethod
    def bit_write(a, b, c):
        pass

    @staticmethod
    def bit_read(a, b):
        pass
