
## cbus.py

import machine
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

    def __init__(self, can=None, config=None, switch=None, led_grn=None, led_ylw=None, params=None, name=None):
        print('** cbus constructor')

        if not isinstance(can, canio.canio):
            raise TypeError('can is not an instance of class canio')

        if not isinstance(config, cbusconfig.cbusconfig):
            raise TypeError('config is not an instance of class cbusconfig')

        self.can = can
        self.config = config

        self.switch = switch
        self.led_grn = led_grn
        self.led_ylw = led_ylw

        if not self.switch and not self.led_grn and not self.led_ylw:
            self.has_ui = False
        else:
            self.has_ui = True

        if params == None:
            self.params = bytearray(20)
        else:
            self.params = params

        if name == None:
            self.name = bytearray(7)
        else:
            self.name = name

        self.event_handler = None
        self.frame_handler = None
        self.long_message_handler = None
        self.opcodes = []

        self.mode_changing = False
        self.in_learn_mode = False
        self.enumerating = False
        self.enum_start_time = 0
        self.enumeration_required = False
        self.enum_responses = [0] * 128
        self.timeout_timer = 0
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

    def set_name(self, name):
        self.name = bytearray(name)

    def set_params(self, params):
        self.params = bytearray(params)

    def set_event_handler(self, event_handler):
        self.event_handler = event_handler

    def set_frame_handler(self, frame_handler, opcodes=[]):
        self.frame_handler = frame_handler
        self.opcodes = opcodes

    def send_cbus_message(self, msg):
        self.can.send_message(msg)
        self.led_grn.pulse()
        self.sent_messages += 1

    def process(self, max_msgs=3):
        #print('** cbus process')

        if self.mode_changing and time.ticks_ms() - self.timeout_timer >= 30000:
            print('mode change timeout')
            self.mode_changing = False;
            self.indicate_mode(self.config.mode)
            self.timeout_timer = 0

        if self.enumeration_required:
            print('enumeration required')
            self.enumeration_required = False
            self.begin_enumeration()

        if self.enumerating and time.ticks_ms() - self.enum_start_time >= 100:
            print('end of enumeration cycle')
            self.process_enumeration_responses()
            self.enumerating = False
            print(f'canid is now {self.config.canid}')

        if self.has_ui:
            self.led_grn.run()
            self.led_ylw.run()

            self.switch.run()

            if self.switch.is_pressed() and self.switch.current_state_duration() >= 6000:
                # print('cbus switch held for 6 seconds - blink')
                self.indicate_mode(cbusconfig.MODE_CHANGING)

            if self.switch.state_changed and not self.switch.is_pressed():

                if self.switch.previous_state_duration >= 6000:
                    print('cbus switch released after 6 seconds, mode change')
                    self.mode_changing = True

                    if self.config.mode == cbusconfig.MODE_SLIM:
                        self.init_flim()
                    elif self.config.mode == cbusconfig.MODE_FLIM:
                        self.revert_slim()

                if self.switch.previous_state_duration <= 2000 and self.switch.previous_state_duration >= 1000:
                    if self.config.mode == cbusconfig.MODE_FLIM:
                        print('flim renegotiate')
                        self.init_flim()

                if self.switch.previous_state_duration <= 1000 and self.switch.previous_state_duration >= 500:
                    if self.config.canid > 0:
                        print('enumerate')
                        self.begin_enumeration()

        processed_msgs = 0

        while self.can.available() and processed_msgs < max_msgs:
            print('processing received messages')

            msg = self.can.get_next_message()

            self.received_messages += 1

            if self.config.mode == cbusconfig.MODE_FLIM:
                # pulse green led
                self.led_grn.pulse()

            if self.sender_canid(msg) == self.config.canid and not self.enumerating:
                # canid clash
                self.enumeration_required = True

            if msg.ext:
                # ignore extended frames
                continue

            if self.frame_handler is not None:
                if self.opcodes is not None and len(self.opcodes) > 0:
                    for opc in opcodes:
                        if msg.data[0] == opc:
                            self.frame_handler(msg)
                            break
                else:
                    self.frame_handler(msg)

            if msg.len > 0:
                try:
                    self.func_tab.get(msg.data[0])(msg)
                except TypeError:
                    print('unhandled opcode = 0x{msg.data[0]:#x}')

            else:
                if msg.rtr and not self.seumerating:
                    self.respond_to_enum_request()
                elif self.enumerating:
                    enum_responses[self.sender_canid(msg)] = 1

            processed_msgs += 1

            print('end of process')

    def handle_accessory_event(self, msg):
        node_number = self.get_node_number_from_message(msg)
        event_number = self.get_event_number_from_message(msg)

        print(f'handle accessory event, {node_number}, {event_number}')

        if self.event_handler is not None:
            i = self.config.find_existing_event(self.get_node_number_from_message(msg), self.get_event_number_from_message(msg))

            if i > -1:
                print(f'found event at index = {i}, calling user handler')
                self.event_handler(msg, i)

    def handle_rqnp(self, msg):
        print('RQNP')

        if self.mode_changing:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_PARAMS
            omsg.data[1] = self.params[1]
            omsg.data[2] = self.params[2]
            omsg.data[3] = self.params[3]
            omsg.data[4] = self.params[4]
            omsg.data[5] = self.params[5]
            omsg.data[6] = self.params[6]
            omsg.data[7] = self.params[7]
            can.send_message(omsg)

    def handle_rqnpn(self, msg):
        print('RQNPN')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            paran = msg.data[3]

            if paran <= self.params[0] and paran < len(self.parans):
                omsg = canmessage.canmessage(self.config.canid, 5)
                omsg.data[0] = cbusdefs.OPC_PARAN
                omsg.data[1] = int(self.config.node_number / 256)
                omsg.data[2] = self.config.node_number & 0xff
                omsg.data[3] = paran
                omsg.data[4] = self.params[paran]
                self.send_cbus_message(omsg)
            else:
                self.sendCMDERR(9)

    def handle_snn(self, msg):
        print('SNN')

        if self.mode_changing:
            self.config.set_node_number(self.get_node_number_from_message(msg))
            omsg = canmessage.canmessage(self.config.canid, 3)
            omsg.data[0] = cbusdefs.OPC_NNACK
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff
            self.send_cbus_message(omsg)

            self.mode_changing = False
            self.config.set_mode(cbusconfig.MODE_FLIM)
            self.indicateMode(cbusconfig.MODE_FLIM);
            self.begin_enumeration()

    def handle_canid(self, msg):
        print('CANID')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            if msg.data[3] < 1 or msg.data[3] > 99:
                self.sendCMDERR(7)
            else:
                self.config.set_canid(msg.data[3])

    def handle_enum(self, msg):
        print('ENUM')

        if self.get_node_number_from_message(msg) == self.config.node_number and self.sender_canid(msg) != self.config.canid and not self.enumerating:
            self.begin_enumeration()

    def handle_nvrd(self, msg):
        print('NVRD')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            if msg.data[3] > self.config.num_nvs:
                self.sendCMDERR(0)
            else:
                omsg = canmessage.canmessage(self.config.canid, 5)
                omsg.data[0] = cbusdefs.OPC_NVANS
                omsg.data[1] = int(self.config.node_number / 256)
                omsg.data[2] = self.config.node_number & 0xff
                omsg.data[3] = msg.data[3]
                omsg.data[4] = self.config.read_nv(msg.data[3])
                self.send_cbus_message(omsg)

    def handle_nvset(self, msg):
        print('NVSET')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            if msg.data[3] > self.config.num_nvs:
                self.sendCMDERR(0)
            else:
                self.config.write_nv(msg.data[3], msg.data[4])
                self.sendWRACK()

    def handle_nnlrn(self, msg):
        print('NNLRN')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            self.in_learn_mode = True
            self.params[8] = self.params[8] | 1 << 5

    def handle_nnuln(self, msg):
        print('NNULN')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            self.in_learn_mode = False
            self.params[8] = self.params[8] % 1 << 5

    def handle_rqevn(self, msg):
        print('RQEVN')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 4)
            omsg.data[0] = cbusdefs.OPC_NUMEV
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = self.config.count_events()
            self.send_cbus_message(omsg)

    def handle_nerd(self, msg):
        print('NERD')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_ENRSP
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff

            for i in range(self.config.num_events):
                event = self.config.read_event(i)
                if event[0] == 255 and event[1] == 255 and event[2] == 255 and event[3] == 255:
                    pass
                else:
                    omsg.data[3] = event[0]
                    omsg.data[4] = event[1]
                    omsg.data[5] = event[2]
                    omsg.data[6] = event[3]
                    omsg.data[7] = i
                    self.send_cbus_message(omsg)
                    time.delay_ms(5)

    def handle_reval(self, msg):
        print('REVAL')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 6)
            omsg.data[0] = cbusdefs.OPC_NEVAL
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = msg.data[3]
            omsg.data[4] = msg.data[4]
            omsg.data[5] = self.config.read_event_ev(msg.data[3], msg.data[4])
            self.send_cbus_message(omsg)

    def handle_nnclr(self, msg):
        print('NNCLR')
        
        if self.get_node_number_from_message(msg) == self.config.node_number and self.in_learn_mode:
            self.config.clear_all_events()
            self.sendWRACK()

    def handle_nnevn(self, msg):
        print('NNEVN')

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 4)
            omsg.data[0] = cbusdefs.OPC_EVNLF
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = self.config.num_events - self.config.count_events()
            self.send_cbus_message(omsg)

    def handle_qnn(self, msg):
        print('QNN')

        if self.config.node_number > 0:
            omsg = canmessage.canmessage(self.config.canid, 6)
            omsg.data[0] = cbusdefs.OPC_PNN
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = self.params[1]
            omsg.data[4] = self.params[3]
            omsg.data[5] = self.params[8]
            send.can.send_message(omsg)

    def handle_rqmn(self, msg):
        print('RQMN')

        if self.mode_changing:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_NAME

            for i in range(len(self.name)):
                omsg.data[i + 1] = self.name[i]

            self.send_cbus_message(omsg)

    def handle_evlrn(self, msg):
        print('EVLRN')

        if self.in_learn_mode:
            if self.config.write_event(lf.get_node_number_from_message(msg), self.get_event_number_from_message(msg), msg.data[5], msg.data[6]):
                self.sendWRACK()
            else:
                self.sendCMDERR(10)

    def handle_evuln(self, msg):
        print('EVULN')

        if self.in_learn_mode:
            if self.config.clear_event(self.get_node_number_from_message(msg), self.get_event_number_from_message(msg)):
                self.sendWRACK()
            else:
                self.sendCMDERR(10)

    def handle_dtxc(self, msg):
        print('DTXC')
        
        if self.long_message_handler is not None:
            self.long_message_handler.handle_Long_message_fragment(msg)

    def send_WRACK(self):
        print('send_WRACK')
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_WRACK
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

    def send_CMDERR(self, err):
        print('send_CMDERR')
        omsg = canmessage.canmessage(self.config.canid, 4)
        omsg.data[0] = cbusdefs.OPC_WRACK
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xff
        omsg.data[3] = err & 0xff
        self.send_cbus_message(omsg)

    def begin_enumeration(self):
        print('begin_enumeration')
        omsg = canmessage.canmessage(self.config.canid, 0)
        omsg.rtr = True
        self.send_cbus_message(omsg)

        self.enum_responses = [0] * 128
        self.num_enum_responses = 0
        self.enumerating = True
        self.enum_start_time = time.ticks_ms()

    def process_enumeration_responses(self):
        print('process_enumeration_responses')
        enum_start_time = 0
        enumerating = False
        new_id = -1

        if self.num_enum_responses == 0:
            print('no enumeration responses received')
            return

        for i in range(1, len(self.enum_responses)):
            if self.enum_responses[i] == 0:
                new_id = i
                break

        if new_id > 0:
            print(f'took unused can id = {new_id}')
            self.config.set_canid(new_id)
            omsg = canmessage.canmessage(self.config.canid, 3)
            omsg.data[0] = cbusdefs.OPC_NNACK
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xff
            self.send_cbus_message(omsg)
        else:
            self.sendCMDERR(7)

    def init_flim(self):
        print('init_flim')
        self.indicate_mode(cbusconfig.MODE_CHANGING)
        self.mode_changing = True
        self.timeout_timer = time.ticks_ms()

        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_RQNN
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

    def revert_slim(self):
        print('revert slim')
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_NNREL
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

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

            self.led_grn.run()
            self.led_ylw.run()

    def set_long_message_handler(self, handler):
        self.long_message_handler = handler

    def get_node_number_from_message(self, msg):
        return (msg.data[1] * 256) + msg.data[2]

    def get_event_number_from_message(self, msg):
        return (msg.data[3] * 256) + msg.data[4]
