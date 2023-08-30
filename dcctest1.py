from machine import UART, Pin
import time

uart = UART(0)
uart.init(baudrate=115200, tx=Pin(12), rx=Pin(13), txbuf=32, rxbuf=128, timeout=1000)

# cmd = "<t -1 27 10 1>"
cmd = "<s>"
uart.write(cmd)

while True:
    res = uart.read()
    print(res)
    time.sleep_ms(100)