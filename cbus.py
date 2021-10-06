
## cbus.py

import machine
import cbusdefs
import time

import canio
import mcp2515
import cbusconfig
import cbusled
import cbusswitch
import cbusdefs
import can_message

class cbus:

    def __init__(self, can=None, config=None):
        print('** cbus constructor')

        if not isinstance(can, canio.canio):
            raise TypeError('can is not an instance of class canio')
        
        if not isinstance(config, cbusconfig.cbusconfig):
            raise TypeError('config is not an instance of class cbusconfig')

        self.switch = None
        self.led_grn = None
        self.led_ylw = None
        self.can = can
        self.config = config
        self.event_handler = None
        self.frame_handler = None
        self.long_message_handler = None
        self.params = None
        self.name = None
        
        self.has_ui = False
        self.mode_changing = False
        self.enumerating = False
        self.enum_timer = 0
        self.timeout_timer = 0
        
        self.enum_responses = bytearray(16)

        self.func_dict = {
            cbusdefs.OPC_ACON:    self.handle_ac_event,
            cbusdefs.OPC_ACOF:    self.handle_ac_event,
            cbusdefs.OPC_ASON:    self.handle_ac_event,
            cbusdefs.OPC_ASOF:    self.handle_ac_event,
            cbusdefs.OPC_ACON1:   self.handle_ac_event,
            cbusdefs.OPC_ACOF1:   self.handle_ac_event,
            cbusdefs.OPC_ASON1:   self.handle_ac_event,
            cbusdefs.OPC_ASOF1:   self.handle_ac_event,
            cbusdefs.OPC_ACON2:   self.handle_ac_event,
            cbusdefs.OPC_ACOF2:   self.handle_ac_event,
            cbusdefs.OPC_ASON2:   self.handle_ac_event,
            cbusdefs.OPC_ASOF2:   self.handle_ac_event,
            cbusdefs.OPC_ACON3:   self.handle_ac_event,
            cbusdefs.OPC_ACOF3:   self.handle_ac_event,
            cbusdefs.OPC_ASON3:   self.handle_ac_event,
            cbusdefs.OPC_ASOF3:   self.handle_ac_event,
            cbusdefs.OPC_RQNP:    self.handle_rqnp,
            cbusdefs.OPC_RQNPN:   self.handle_rqnpn,
            cbusdefs.OPC_SNN:     self.handle_snn,
            cbusdefs.OPC_CANID:   self.handle_canid,
            cbusdefs.OPC_ENUM:    self.handle_enum,
            cbusdefs.OPC_NVRD:    self.handle_nvrd,
            cbusdefs.OPC_NVSET:   self.handle_nvset,
            cbusdefs.OPC_NNLRN:   self.handle_nnlrn,
            cbusdefs.OPC_NNULN:   self.handle_nnuln,
            cbusdefs.OPC_RQEVN:   self.handle_rqevn,
            cbusdefs.OPC_NERD:    self.handle_nerd,
            cbusdefs.OPC_REVAL:   self.handle_reval,
            cbusdefs.OPC_NNCLR:   self.handle_nnclr,
            cbusdefs.OPC_NNEVN:   self.handle_nnevn,
            cbusdefs.OPC_QNN:     self.handle_qnn,
            cbusdefs.OPC_RQMN:    self.handle_rqmn,
            cbusdefs.OPC_EVLRN:   self.handle_evlrn,
            cbusdefs.OPC_EVULN:   self.handle_evuln,
            cbusdefs.OPC_DTXC:    self.handle_dtxc
        }

    def begin(self):
        self.can.begin()
        self.config.begin()
        self.indicate_mode(self.config.mode)
        
    def set_config(self, config):
        self.config = config
        pass

    def set_switch(self, pin):
        self.switch = cbusswitch.cbusswitch(pin)
        self.has_ui = True
        
    def set_leds(self, grn_pin, ylw_pin):
        self.led_grn = cbusled.cbusled(grn_pin)
        self.led_ylw = cbusled.cbusled(ylw_pin)
        self.has_ui = True

    def process(self, max_msgs = 3):
        print('** cbus process')

        self.led_grn.run()
        self.led_ylw.run()

        self.switch.run()

        msgs = 0

        while self.can.available() and msg < max_msgs:
            msg = can.get_next_message()

            if msg.len > 0:
                try:
                    func_dict.get(msg.data[0])(msg)
                except TypeError:
                    print('unhandled opcode = {msg.data[0]:#x}')

    def handle_ac_event(self, msg):
        print('handle accessory event')

    def handle_rqnp(self, msg):
        print('RQNP')

    def handle_rqnpn(self, msg):
        print('RQNPN')

    def handle_snn(self, msg):
        print('SNN')

    def handle_canid(self, msg):
        print('CANID')

    def handle_enum(self, msg):
        print('ENUM')

    def handle_nvrd(self, msg):
        print('NVRD')

    def handle_nvset(self, msg):
        print('NVSET')

    def handle_nnlrn(self, msg):
        print('NNLRN')

    def handle_nnuln(self, msg):
        print('NNULN')

    def handle_rqevn(self, msg):
        print('RQEVN')

    def handle_nerd(self, msg):
        print('NERD')

    def handle_reval(self, msg):
        print('REVAL')

    def handle_nnclr(self, msg):
        print('NNCLR')

    def handle_nnevn(self, msg):
        print('NNEVN')

    def handle_qnn(self, msg):
        print('QNN')

    def handle_rqmn(self, msg):
        print('RQMN')

    def handle_evlrn(self, msg):
        print('EVLRN')

    def handle_evuln(self, msg):
        print('EVULN')

    def handle_dtxc(self, msg):
        print('DTXC')

    def send_WRACK(self):
        msg = can_message.can_message()
        msg.len = 3
        msg.data[0] = cbusdefs.OPC_WRACK
        msg.data[1] = int(config.node_number / 255)
        msg.data[2] = config.node_number & 0xff
        can.send_message(msg)

    def send_CMDERR(self, err):
        msg = can_message.can_message()
        msg.len = 4
        msg.data[0] = cbusdefs.OPC_WRACK
        msg.data[1] = int(config.node_number / 255)
        msg.data[2] = config.node_number & 0xff
        msg.data[3] = err & 0xff
        can.send_message(msg)

    def CAN_enumeration(self):
        self.enum_responses = bytearray(16)
        self.enum_timer = time.ticks_ms()
        self.enumerating = True

        msg = can_message.can_message()
        msg.len = 0
        msg.rtr = True
        can.send_message(msg)

    def init_flim(self):
        self.indicate_mode(cbusconfig.MODE_CHANGING)
        self.mode_changing = true
        self.timeout_timer = time.ticks_ms()

        msg = can_message.can_message()
        msg.len = 3
        msg.data[0] = cbusdefs.OPC_RQNN
        msg.data[1] = int(config.node_number / 255)
        msg.data[2] = config.node_number & 0xff
        can.send_message(msg)

    def revert_slim(self):
        msg = can_message.can_message()
        msg.len = 3
        msg.data[0] = cbusdefs.OPC_NNREL
        msg.data[1] = int(config.node_number / 255)
        msg.data[2] = config.node_number & 0xff
        can.send_message(msg)

        self.mode_changing = False;
        config.set_mode(config.MODE_SLIM)
        config.set_canid(0)
        config.set_node_number(0)
        self.indicate_mode(cbusconfig.MODE_SLIM)

    def get_sender_canid(self, msg):
        return (msg.id & 0x7f)

    def indicate_mode(self, mode):

        if self.has_ui:
            if mode == cbusconfig.MODE_SLIM:
                self.led_grn.on()
                self.led_ylw.off()
            elif mode == cbusconfig.MODE_FLIM:
                self.led_grn.off()
                self.led_ylw.on()
            elif mode == cbusconfig.MODE_CHANGING:
                self.led_grn.off()
                self.led_ylw.blink()
            else:
                print('unknown mode')

    def handle_accessory_event(self, node_number, event_number):
        pass

    def set_long_message_handler(self):
        pass
    
    
    