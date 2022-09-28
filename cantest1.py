
## cantest1.py

import time, _thread
import mcp2515, cbus, cbusdefs, cbusconfig, canmessage, cbuslongmessage, i2ceeprom

thread_can_run = False
thread_is_running = False

def run_cbus_thread():
    global thread_can_run
    global thread_is_running

    thread_is_running = True
    cbus.led_grn.pulse()
    
    while thread_can_run:
        cbus.process()
        time.sleep_ms(5)

    thread_is_running = False
    _thread.exit()

def start_cbus():
    global thread_can_run
    global thread_is_running
    
    if thread_is_running:
        print('cbus thread is already running')
        return False

    print('starting cbus thread')
    thread_can_run = True
    _thread.start_new_thread(run_cbus_thread, ())
    print('cbus thread started')
    return True

def stop_cbus():
    global thread_can_run
    global thread_is_running
    
    if (not thread_is_running):
        print('cbus thread is not running')
        return False

    print('stopping cbus thread')
    thread_can_run = False
    return True

def event_handler(msg, idx):
    print(f'user event handler: index = {idx}')
    msg.print()
    print(f'ev1 = {cbus.config.read_event_ev(idx, 1)}')

def frame_handler(msg):
    print('user frame handler:')
    msg.print()

def long_message_handler(message, streamid, status):
    print(f'user long message handler: status = {status}')

def flim():
    cbus.config.set_mode(1)
    cbus.config.set_canid(5)
    cbus.config.set_node_number(333)
    cbus.config.reboot()


#
# execution starts here
#

start_time = time.ticks_ms()
print('** module starting')

cbus = cbus.cbus(mcp2515.mcp2515(), cbusconfig.cbusconfig())

MODULE_ID = 103
module_name = 'PYCO   '
module_params = [20,
                 cbusdefs.MANU_MERG,
                 0,
                 MODULE_ID,
                 cbus.config.num_events,
                 cbus.config.num_evs,
                 cbus.config.num_nvs,
                 1,
                 7,
                 0,
                 cbusdefs.PB_CAN,
                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

cbus.set_switch(22)
cbus.set_leds(21, 20)
cbus.set_name(module_name)
cbus.set_params(module_params)
cbus.set_event_handler(event_handler)
cbus.set_frame_handler(frame_handler)

cbus.begin()

msg2 = canmessage.canmessage(1234, 5, [0xe9, 1, 0, 0, 24, 0, 0, 0])
msg3 = canmessage.canmessage(1234, 5, [0x91, 0, 22, 0, 22, 0, 0, 0])

lm = cbuslongmessage.cbuslongmessage(cbus)
lm.subscribe([1, 2, 3, 4, 5], long_message_handler)

start_cbus()

print()
print('** startup complete');
print(f'module: name = {module_name}, mode = {cbus.config.mode}, can id = {cbus.config.canid}, node number = {cbus.config.node_number}')
print(f'free memory = {cbus.config.free_memory()} bytes')
print(f'startup time = {time.ticks_ms() - start_time} ms')

