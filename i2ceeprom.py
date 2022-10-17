
# i2ceeprom.py

# routines to address I2C serial EEPROM and store module config data
# SDA = pin 16, SCL = pin 17

import time
from machine import Pin, I2C, SoftI2C

class i2ceeprom():
   
    def __init__(self, i2caddr=0x50, scl_pin=17, sda_pin=16, size=8192):
        print('** i2ceeprom constructor')

        self.i2caddr = i2caddr
        self.freq = 400000
        # self.bus = SoftI2C(scl=Pin(scl_pin), sda=Pin(sda_pin), freq=400_000)
        self.bus = I2C(0, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=400_000)

        slaves = self.bus.scan()
        print(f'found devices: {slaves}')

        self._addrbuf = bytearray(2)
        self._databuf = bytearray(1)
        self.set_size(size)

    def set_size(self, size):
        self.size = size

    def read(self, addr):
        self._addrbuf[0] = (addr >> 8) & 0xff
        self._addrbuf[1] = addr & 0xff

        self.bus.writeto(self.i2caddr, self._addrbuf)
        data = self.bus.readfrom(self.i2caddr, 1)
        return data

    def write(self, addr, data):
        t = bytearray(3)
        t[0] = (addr >> 8) & 0xff
        t[1] = addr & 0xff
        t[2] = data & 0xff

        self.bus.writeto(self.i2caddr, t)
        time.sleep_ms(5)

    def erase(self):
        for x in range(0, self.size - 1):
            self.write(x, 255)

