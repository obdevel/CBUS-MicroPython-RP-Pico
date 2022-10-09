# CBUS in MicroPython on the RP Pico RP2040

Initial attempt at a MERG CBUS module in MicroPython running on the RP2040 Pico
using an MCP2515 CAN controller IC

The code should, in principle, run on any hardware supported by MicroPython, although some
board-specific changes may be required. The same applies if different pins are used for external connections,
to e.g. the SPI bus, LEDs, switch, etc.

A CBUS module is implemented in module.py, which imports the supporting Python modules and contains
the boilerplate code.

boot.py is run at startup to autorun the code, if required.

Simply upload all the files to the root directory (/) of the Pico.