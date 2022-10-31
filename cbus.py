# cbus.py

import time
import uasyncio as asyncio
import canio
import cbusconfig
import cbusled
import cbusswitch
import cbusdefs
import canmessage
import cbushistory
import logger

MODE_SLIM = 0
MODE_FLIM = 1
MODE_CHANGING = 2

MSGS_EVENTS_ONLY = 0
MSGS_ALL = 1

event_opcodes = [
    cbusdefs.OPC_ACON,
    cbusdefs.OPC_ACOF,
    cbusdefs.OPC_ASON,
    cbusdefs.OPC_ASOF,
    cbusdefs.OPC_ACON1,
    cbusdefs.OPC_ACOF1,
    cbusdefs.OPC_ASON1,
    cbusdefs.OPC_ASOF1,
    cbusdefs.OPC_ACON2,
    cbusdefs.OPC_ACOF2,
    cbusdefs.OPC_ASON2,
    cbusdefs.OPC_ASOF2,
]


class cbus:
    def __init__(
        self,
        can=None,
        config=None,
        switch=None,
        led_grn=None,
        led_ylw=None,
        params=None,
        name=None,
    ):

        self.logger = logger.logger()
        # self.logger.log("cbus constructor")

        if can and not isinstance(can, canio.canio):
            raise TypeError("error: can is not an instance of class canio")

        if config and not isinstance(config, cbusconfig.cbusconfig):
            raise TypeError("error: config is not an instance of class cbusconfig")

        self.can = can
        self.config = config

        self.switch = switch
        self.led_grn = led_grn
        self.led_ylw = led_ylw

        if not self.switch or not self.led_grn or not self.led_ylw:
            self.has_ui = False
        else:
            self.has_ui = True

        if params is None:
            self.params = []
        else:
            self.params = params

        if name is None:
            self.name = bytearray(7)
        else:
            self.name = name

        self.event_handler = None
        self.frame_handler = None
        self.long_message_handler = None
        self.opcodes = []

        self.consume_own_messages = False
        self.messages_to_consume = MSGS_ALL
        self.history = None

        self.gridconnect_server = None

        self.in_transition = False
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
            cbusdefs.OPC_ACON: self.handle_accessory_event,
            cbusdefs.OPC_ACOF: self.handle_accessory_event,
            cbusdefs.OPC_ASON: self.handle_accessory_event,
            cbusdefs.OPC_ASOF: self.handle_accessory_event,
            cbusdefs.OPC_ACON1: self.handle_accessory_event,
            cbusdefs.OPC_ACOF1: self.handle_accessory_event,
            cbusdefs.OPC_ASON1: self.handle_accessory_event,
            cbusdefs.OPC_ASOF1: self.handle_accessory_event,
            cbusdefs.OPC_ACON2: self.handle_accessory_event,
            cbusdefs.OPC_ACOF2: self.handle_accessory_event,
            cbusdefs.OPC_ASON2: self.handle_accessory_event,
            cbusdefs.OPC_ASOF2: self.handle_accessory_event,
            cbusdefs.OPC_ACON3: self.handle_accessory_event,
            cbusdefs.OPC_ACOF3: self.handle_accessory_event,
            cbusdefs.OPC_ASON3: self.handle_accessory_event,
            cbusdefs.OPC_ASOF3: self.handle_accessory_event,
            cbusdefs.OPC_RQNP: self.handle_rqnp,
            cbusdefs.OPC_RQNPN: self.handle_rqnpn,
            cbusdefs.OPC_SNN: self.handle_snn,
            cbusdefs.OPC_CANID: self.handle_canid,
            cbusdefs.OPC_ENUM: self.handle_enum,
            cbusdefs.OPC_NVRD: self.handle_nvrd,
            cbusdefs.OPC_NVSET: self.handle_nvset,
            cbusdefs.OPC_NNLRN: self.handle_nnlrn,
            cbusdefs.OPC_NNULN: self.handle_nnuln,
            cbusdefs.OPC_RQEVN: self.handle_rqevn,
            cbusdefs.OPC_NERD: self.handle_nerd,
            cbusdefs.OPC_REVAL: self.handle_reval,
            cbusdefs.OPC_NNCLR: self.handle_nnclr,
            cbusdefs.OPC_NNEVN: self.handle_nnevn,
            cbusdefs.OPC_QNN: self.handle_qnn,
            cbusdefs.OPC_RQMN: self.handle_rqmn,
            cbusdefs.OPC_EVLRN: self.handle_evlrn,
            cbusdefs.OPC_EVULN: self.handle_evuln,
            cbusdefs.OPC_DTXC: self.handle_dtxc,
        }

    def begin(self):
        # self.logger.log("cbus begin")
        self.can.begin()
        self.config.begin()
        self.has_ui and self.indicate_mode(self.config.mode)

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
        self.params = params

    def set_event_handler(self, event_handler):
        self.event_handler = event_handler

    def set_frame_handler(self, frame_handler, opcodes=[]):
        self.frame_handler = frame_handler
        self.opcodes = opcodes

    def set_consume_own_messages(self, consume, which=MSGS_ALL):
        self.consume_own_messages = consume
        self.messages_to_consume = which

    def send_cbus_message(self, msg):
        msg.make_header()
        self.send_cbus_message_no_header_update(msg)

    def send_cbus_message_no_header_update(self, msg):
        self.can.send_message(msg)
        self.has_ui and self.config.mode == MODE_FLIM and self.led_grn.pulse()
        self.sent_messages += 1

        if self.history is not None:
            self.history.add(msg)

        if self.consume_own_messages:
            self.can.rx_queue.enqueue(msg)

    def set_can(self, can):
        if can and not isinstance(can, canio.canio):
            raise TypeError("error: can is not an instance of class canio")
        else:
            self.can = can

    def set_config(self, config):
        if config and not isinstance(config, cbusconfig.cbusconfig):
            raise TypeError("error: config is not an instance of class cbusconfig")
        else:
            set.config = config

    def process(self, max_msgs=3):
        start_time = time.ticks_ms()

        if self.in_transition and time.ticks_ms() - self.timeout_timer >= 30000:
            self.logger.log("mode change timeout")
            self.in_transition = False
            self.indicate_mode(self.config.mode)
            self.timeout_timer = 0

        if self.enumeration_required:
            self.logger.log("enumeration required")
            self.enumeration_required = False
            self.begin_enumeration()

        if self.enumerating and time.ticks_ms() - self.enum_start_time >= 100:
            self.logger.log("end of enumeration cycle")
            self.process_enumeration_responses()
            self.enumerating = False
            self.logger.log(f"canid is now {self.config.canid}")

        if self.has_ui:
            self.led_grn.run()
            self.led_ylw.run()
            self.switch.run()

            if (
                self.switch.is_pressed()
                and self.switch.current_state_duration() >= 6000
            ):
                # self.logger.log('cbus switch held for 6 seconds - blink')
                self.indicate_mode(MODE_CHANGING)

            if self.switch.state_changed and not self.switch.is_pressed():

                if self.switch.previous_state_duration >= 6000:
                    self.logger.log("cbus switch released after 6 seconds, mode change")
                    self.in_transition = True

                    if self.config.mode == MODE_SLIM:
                        self.init_flim()
                    elif self.config.mode == MODE_FLIM:
                        self.revert_slim()

                if (
                    self.switch.previous_state_duration <= 2000
                    and self.switch.previous_state_duration >= 1000
                ):
                    if self.config.mode == MODE_FLIM:
                        self.logger.log("flim renegotiate")
                        self.init_flim()

                if (
                    self.switch.previous_state_duration <= 1000
                    and self.switch.previous_state_duration >= 250
                ):
                    if self.config.canid > 0:
                        self.logger.log("enumerate")
                        self.begin_enumeration()

        processed_msgs = 0

        while self.can.available() and processed_msgs < max_msgs:
            # self.logger.log(f'process: processing received messages, max = {max_msgs}, curr = {processed_msgs}')

            msg = self.can.get_next_message()

            self.received_messages += 1

            if self.history is not None:
                self.history.add(msg)

            if self.gridconnect_server is not None:
                self.gridconnect_server.output_queue.enqueue(msg)

            if self.config.mode == MODE_FLIM:
                # pulse green led
                self.led_grn.pulse()

            if msg.get_canid() == self.config.canid and not self.enumerating:
                # canid clash
                self.logger.log("canid clash")
                self.enumeration_required = True

            if msg.ext:
                # ignore extended frames
                continue

            if self.frame_handler is not None:
                if self.opcodes is not None and len(self.opcodes) > 0:
                    for opc in self.opcodes:
                        if msg.data[0] == opc:
                            self.frame_handler(msg)
                            break
                else:
                    self.frame_handler(msg)

            if msg.len > 0:
                try:
                    # self.logger.log(f'looking up opcode = {msg.data[0]:#x}')
                    self.func_tab.get(msg.data[0])(msg)
                except TypeError:
                    self.logger.log(f"unhandled opcode = 0x{msg.data[0]:#x}")

            else:
                if msg.rtr and not self.enumerating:
                    self.logger.log("enum response requested by another node")
                    self.respond_to_enum_request()
                elif self.enumerating:
                    self.logger.log("got enum response")
                    self.enum_responses[msg.get_canid()] = 1
                    self.num_enum_responses += 1

            processed_msgs += 1

        run_time = time.ticks_ms() - start_time

        if processed_msgs > 0:
            pass
            # self.logger.log(f'end of process, msgs = {processed_msgs}, run time = {run_time}')
            # self.logger.log()

        return processed_msgs

    def handle_accessory_event(self, msg):
        # self.logger.log('handle_accessory_event:')

        if self.event_handler is not None:
            node_number, event_number = self.get_node_and_event_numbers_from_message(
                msg
            )
            idx = self.config.find_existing_event(node_number, event_number)

            if idx > -1:
                # self.logger.log(f'calling user handler')
                self.event_handler(msg, idx)

    def handle_rqnp(self, msg):
        self.logger.log("RQNP")

        if self.in_transition:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_PARAMS
            omsg.data[1] = self.params[1]
            omsg.data[2] = self.params[2]
            omsg.data[3] = self.params[3]
            omsg.data[4] = self.params[4]
            omsg.data[5] = self.params[5]
            omsg.data[6] = self.params[6]
            omsg.data[7] = self.params[7]
            self.send_cbus_message(omsg)

    def handle_rqnpn(self, msg):
        self.logger.log("RQNPN")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            paran = msg.data[3]

            if paran <= self.params[0] and paran < len(self.parans):
                omsg = canmessage.canmessage(self.config.canid, 5)
                omsg.data[0] = cbusdefs.OPC_PARAN
                omsg.data[1] = int(self.config.node_number / 256)
                omsg.data[2] = self.config.node_number & 0xFF
                omsg.data[3] = paran
                omsg.data[4] = self.params[paran]
                self.send_cbus_message(omsg)
            else:
                self.sendCMDERR(9)

    def handle_snn(self, msg):
        self.logger.log("SNN")

        if self.in_transition:
            self.config.set_node_number(self.get_node_number_from_message(msg))
            omsg = canmessage.canmessage(self.config.canid, 3)
            omsg.data[0] = cbusdefs.OPC_NNACK
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF
            self.send_cbus_message(omsg)

            self.in_transition = False
            self.config.set_mode(MODE_FLIM)
            self.indicateMode(MODE_FLIM)
            self.enumeration_required = True

    def handle_canid(self, msg):
        self.logger.log("CANID")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            if msg.data[3] < 1 or msg.data[3] > 99:
                self.sendCMDERR(7)
            else:
                self.config.set_canid(msg.data[3])

    def handle_enum(self, msg):
        self.logger.log("ENUM")

        if (
            self.get_node_number_from_message(msg) == self.config.node_number
            and msg.get_canid() != self.config.canid
            and not self.enumerating
        ):
            self.begin_enumeration()

    def handle_nvrd(self, msg):
        self.logger.log("NVRD")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            if msg.data[3] > self.config.num_nvs:
                self.sendCMDERR(0)
            else:
                omsg = canmessage.canmessage(self.config.canid, 5)
                omsg.data[0] = cbusdefs.OPC_NVANS
                omsg.data[1] = int(self.config.node_number / 256)
                omsg.data[2] = self.config.node_number & 0xFF
                omsg.data[3] = msg.data[3]
                omsg.data[4] = self.config.read_nv(msg.data[3])
                self.send_cbus_message(omsg)

    def handle_nvset(self, msg):
        self.logger.log("NVSET")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            if msg.data[3] > self.config.num_nvs:
                self.sendCMDERR(0)
            else:
                self.config.write_nv(msg.data[3], msg.data[4])
                self.sendWRACK()

    def handle_nnlrn(self, msg):
        self.logger.log("NNLRN")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            self.in_learn_mode = True
            self.params[8] = self.params[8] | 1 << 5

    def handle_nnuln(self, msg):
        self.logger.log("NNULN")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            self.in_learn_mode = False
            self.params[8] = self.params[8] % 1 << 5

    def handle_rqevn(self, msg):
        self.logger.log("RQEVN")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 4)
            omsg.data[0] = cbusdefs.OPC_NUMEV
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF
            omsg.data[3] = self.config.count_events()
            self.send_cbus_message(omsg)

    def handle_nerd(self, msg):
        self.logger.log("NERD")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_ENRSP
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF

            for i in range(self.config.num_events):
                event = self.config.read_event(i)
                if (
                    event[0] == 255
                    and event[1] == 255
                    and event[2] == 255
                    and event[3] == 255
                ):
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
        self.logger.log("REVAL")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 6)
            omsg.data[0] = cbusdefs.OPC_NEVAL
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF
            omsg.data[3] = msg.data[3]
            omsg.data[4] = msg.data[4]
            omsg.data[5] = self.config.read_event_ev(msg.data[3], msg.data[4])
            self.send_cbus_message(omsg)

    def handle_nnclr(self, msg):
        self.logger.log("NNCLR")

        if (
            self.get_node_number_from_message(msg) == self.config.node_number
            and self.in_learn_mode
        ):
            self.config.clear_all_events()
            self.sendWRACK()

    def handle_nnevn(self, msg):
        self.logger.log("NNEVN")

        if self.get_node_number_from_message(msg) == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 4)
            omsg.data[0] = cbusdefs.OPC_EVNLF
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF
            omsg.data[3] = self.config.num_events - self.config.count_events()
            self.send_cbus_message(omsg)

    def handle_qnn(self, msg):
        self.logger.log("QNN")

        if self.config.node_number > 0:
            omsg = canmessage.canmessage(self.config.canid, 6)
            omsg.data[0] = cbusdefs.OPC_PNN
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF
            omsg.data[3] = self.params[1]
            omsg.data[4] = self.params[3]
            omsg.data[5] = self.params[8]
            self.send_cbus_message(omsg)

    def handle_rqmn(self, msg):
        self.logger.log("RQMN")

        if self.in_transition:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_NAME

            for i in range(len(self.name)):
                omsg.data[i + 1] = self.name[i]

            self.send_cbus_message(omsg)

    def handle_evlrn(self, msg):
        self.logger.log("EVLRN")

        if self.in_learn_mode:
            if self.config.write_event(
                self.get_node_number_from_message(msg),
                self.get_event_number_from_message(msg),
                msg.data[5],
                msg.data[6],
            ):
                self.sendWRACK()
            else:
                self.sendCMDERR(10)

    def handle_evuln(self, msg):
        self.logger.log("EVULN")

        if self.in_learn_mode:
            if self.config.clear_event(
                self.get_node_number_from_message(msg),
                self.get_event_number_from_message(msg),
            ):
                self.sendWRACK()
            else:
                self.sendCMDERR(10)

    def handle_dtxc(self, msg):
        self.logger.log("DTXC")

        if self.long_message_handler is not None:
            self.long_message_handler.handle_long_message_fragment(msg)

    def send_WRACK(self):
        self.logger.log("send_WRACK")
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_WRACK
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xFF
        self.send_cbus_message(omsg)

    def send_CMDERR(self, err):
        self.logger.log("send_CMDERR")
        omsg = canmessage.canmessage(self.config.canid, 4)
        omsg.data[0] = cbusdefs.OPC_WRACK
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xFF
        omsg.data[3] = err & 0xFF
        self.send_cbus_message(omsg)

    def begin_enumeration(self):
        self.logger.log("begin_enumeration")
        omsg = canmessage.canmessage(self.config.canid, 0)
        omsg.rtr = True
        self.send_cbus_message(omsg)

        self.enum_responses = [0] * 128
        self.num_enum_responses = 0
        self.enumerating = True
        self.enum_start_time = time.ticks_ms()

    def process_enumeration_responses(self):
        self.logger.log("process_enumeration_responses")
        self.enum_start_time = 0
        self.enumerating = False
        new_id = -1

        if self.num_enum_responses == 0:
            self.logger.log("no enumeration responses received")
            return

        for i in range(1, len(self.enum_responses)):
            if self.enum_responses[i] == 0:
                new_id = i
                break

        if new_id > 0:
            self.logger.log(f"took unused can id = {new_id}")
            self.config.set_canid(new_id)
            omsg = canmessage.canmessage(self.config.canid, 3)
            omsg.data[0] = cbusdefs.OPC_NNACK
            omsg.data[1] = int(self.config.node_number / 256)
            omsg.data[2] = self.config.node_number & 0xFF
            self.send_cbus_message(omsg)
        else:
            self.sendCMDERR(7)

    def init_flim(self):
        self.logger.log("init_flim")
        self.indicate_mode(MODE_CHANGING)
        self.in_transition = True
        self.timeout_timer = time.ticks_ms()

        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_RQNN
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xFF
        self.send_cbus_message(omsg)

    def revert_slim(self):
        self.logger.log("revert slim")
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_NNREL
        omsg.data[1] = int(self.config.node_number / 256)
        omsg.data[2] = self.config.node_number & 0xFF
        self.send_cbus_message(omsg)

        self.in_transition = False
        self.config.set_mode(MODE_SLIM)
        self.config.set_canid(0)
        self.config.set_node_number(0)
        self.indicate_mode(MODE_SLIM)

    def respond_to_enum_request(self):
        self.logger.log("respond to enum request")
        omsg = canmessage.canmessage(self.config.canid, 0)
        self.send_cbus_message(omsg)

    def indicate_mode(self, mode):

        if self.has_ui:
            if mode == MODE_SLIM:
                self.led_grn.on()
                self.led_ylw.off()
            elif mode == MODE_FLIM:
                self.led_grn.off()
                self.led_ylw.on()
            elif mode == MODE_CHANGING:
                self.led_grn.off()
                self.led_ylw.blink()
            else:
                self.logger.log("unknown mode")

            self.led_grn.run()
            self.led_ylw.run()

    def set_long_message_handler(self, handler):
        self.long_message_handler = handler

    def get_node_number_from_message(self, msg):
        return (msg.data[1] * 256) + msg.data[2]

    def get_event_number_from_message(self, msg):
        return (msg.data[3] * 256) + msg.data[4]

    def get_node_and_event_numbers_from_message(self, msg):
        return (
            ((msg.data[1] * 256) + msg.data[2]),
            ((msg.data[3] * 256) + msg.data[4]),
        )

    def set_history(self, history):
        if isinstance(history, cbushistory.cbushistory):
            self.history = history
        else:
            self.logger.log("*error: history object is not an instance of cbushistory")

    def message_opcode_is_event(self, msg):
        return msg.data[0] in event_opcodes

    def set_gcserver(self, server):
        import gcserver
        self.gridconnect_server = server
