
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
import canmessage
import cbuslongmessage

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
        self.enum_start = 0
        self.enumeration_required = False
        self.in_learn_mode = False
        self.in_setup_mode = False
        self.timeout_timer = 0

        self.enum_responses = [0] * 128
        self.num_enum_responses = 0

        self.received_messages = 0
        self.sent_messages = 0

        self.func_tab = {
            cbusdefs.OPC_ACON:    self.handle_accessory_event,
            cbusdefs.OPC_ACOF:    self.handle_accessory_event,
            cbusdefs.OPC_ASON:    self.handle_accessory_event,
            cbusdefs.OPC_ASOF:    self.handle_accessory_event,
            cbusdefs.OPC_ACON1:   self.handle_accessory_event,
            cbusdefs.OPC_ACOF1:   self.handle_accessory_event,
            cbusdefs.OPC_ASON1:   self.handle_accessory_event,
            cbusdefs.OPC_ASOF1:   self.handle_accessory_event,
            cbusdefs.OPC_ACON2:   self.handle_accessory_event,
            cbusdefs.OPC_ACOF2:   self.handle_accessory_event,
            cbusdefs.OPC_ASON2:   self.handle_accessory_event,
            cbusdefs.OPC_ASOF2:   self.handle_accessory_event,
            cbusdefs.OPC_ACON3:   self.handle_accessory_event,
            cbusdefs.OPC_ACOF3:   self.handle_accessory_event,
            cbusdefs.OPC_ASON3:   self.handle_accessory_event,
            cbusdefs.OPC_ASOF3:   self.handle_accessory_event,
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
        #print('** cbus process')

        if self.enumeration_required:
            self.enumeration_required = False
            self.begin_enumeration()

        if self.enumerating and time.tick_ms() - self.enum_start >= 100:
            self.process_enum_responses()

        if self.has_ui:
            self.led_grn.run()
            self.led_ylw.run()

            self.switch.run()

        processed_msgs = 0
        
        if self.frame_handler is not None:
            self.frame_handler(msg)

        while self.can.available() and processed_msgs < max_msgs:
            msg = self.can.get_next_message()
            
            if self.remote_canid(msg) == self.config.canid:
                self.enumeration_required = True

            if msg.len > 0:

                node_number = (msg.data[1] * 256) + msg.data[2]
                event_number = (msg.data[3] * 256) + msg.data[4]

                try:
                    self.func_tab.get(msg.data[0])(msg)
                except TypeError:
                    print('unhandled opcode = 0x{msg.data[0]:#x}')

            else:
                if msg.rtr:
                    self.respond_to_enum_request()

            processed_msgs += 1
            received_messages += 1

    def handle_accessory_event(self, msg):
        print('handle accessory event')
        
        if self.event_handler is not None:
            self.event_handler(msg)

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
        
        if self.long_message_handler is not None:
            self.long_message_handler.handle_Long_message_fragment(msg)

    def send_WRACK(self):
        msg = canmessage.canmessage()
        msg.len = 3
        msg.data[0] = cbusdefs.OPC_WRACK
        msg.data[1] = int(self.config.node_number / 256)
        msg.data[2] = self.config.node_number & 0xff
        self.can.send_message(msg)

    def send_CMDERR(self, err):
        msg = canmessage.canmessage()
        msg.len = 4
        msg.data[0] = cbusdefs.OPC_WRACK
        msg.data[1] = int(self.config.node_number / 256)
        msg.data[2] = self.config.node_number & 0xff
        msg.data[3] = err & 0xff
        self.can.send_message(msg)

    def begin_enumeration(self):
        msg = canmessage.canmessage()
        msg.len = 0
        msg.rtr = True
        self.can.send_message(msg)

        self.enum_responses = bytearray(16)
        self.num_enum_responses = 0
        self.enumerating = True
        self.enum_start = time.ticks_ms()

    def process_enum_responses(self):
        enum_start = 0
        enumerating = False
        new_id = -1

        if self.num_enum_responses == 0:
            return

        for i in range(1, 128):
            if self.enum_responses[i] == 0:
                new_id = i
                break

        if new_id > -1:
            print(f'took can id = {new_id}')
            self.config.set_canid(new_id)
            # send NNACK
        else:
            self.sendCMDERR(7)

    def init_flim(self):
        self.indicate_mode(cbusconfig.MODE_CHANGING)
        self.mode_changing = True
        self.timeout_timer = time.ticks_ms()

        msg = canmessage.canmessage()
        msg.len = 3
        msg.data[0] = cbusdefs.OPC_RQNN
        msg.data[1] = int(self.config.node_number / 256)
        msg.data[2] = self.config.node_number & 0xff
        self.can.send_message(msg)

    def revert_slim(self):
        msg = canmessage.canmessage()
        msg.len = 3
        msg.data[0] = cbusdefs.OPC_NNREL
        msg.data[1] = int(self.config.node_number / 256)
        msg.data[2] = self.config.node_number & 0xff
        self.can.send_message(msg)

        self.mode_changing = False;
        self.config.set_mode(cbusconfig.MODE_SLIM)
        self.config.set_canid(0)
        self.config.set_node_number(0)
        self.indicate_mode(cbusconfig.MODE_SLIM)

    def respond_to_enum_request(self):
        pass

    def sender_canid(self, msg):
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

    def set_long_message_handler(self, handler):
        self.long_message_handler = handler

    