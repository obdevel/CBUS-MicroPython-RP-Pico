# classes to represent various hardware implementations
# saves time by not having to specific individual pins in
# application program

from machine import SPI, Pin
import mcp2515

# base class
class cbus_board:
    def __init__(self):
        self.bus = None
        self.controller = None
        self.switch_pin_number = -1
        self.green_led_pin_number = -1
        self.yellow_led_pin_number = -1

# implementation of DG board
class dgboard(cbus_board):
    def __init__(self):
        super().__init__()
        self.bus = SPI(0, baudrate=10_000_000, polarity=0, phase=0, bits=8, firstbit=SPI.MSB, sck=Pin(2), mosi=Pin(3), miso=Pin(4))
        self.can = mcp2515.mcp2515(osc=16_000_000, cs_pin=5, interrupt_pin=1, bus=self.bus)
        self.switch_pin_number = 22
        self.green_led_pin_number = 21
        self.yellow_led_pin_number = 20
