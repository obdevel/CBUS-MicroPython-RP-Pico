# cbus.py

import time

import uasyncio as asyncio
from micropython import const

import canio
import canmessage
import cbusconfig
import cbusdefs
import cbushistory
import cbusled
import cbuspubsub
import cbusswitch
import logger

MODE_SLIM = const(0)
MODE_FLIM = const(1)
MODE_CHANGING = const(2)

MSGS_EVENTS_ONLY = const(0)
MSGS_ALL = const(1)


class cbus:
    def __init__(
            self,
            can: canio.canio,
            config: cbusconfig.cbusconfig,
            switch: cbusswitch.cbusswitch = None,
            led_grn: cbusled.cbusled = None,
            led_ylw: cbusled.cbusled = None,
            params: list = None,
            name: bytes = None,
    ):

        self.logger = logger.logger()

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
            self.params = ()
        else:
            self.params = params

        if name is None:
            self.name = bytearray(7)
        else:
            self.name = name

        self.poll = False

        self.event_handler = None
        self.opcodes = ()
        self.received_message_handler = None
        self.sent_message_handler = None
        self.long_message_handler = None

        self.consume_own_messages = False
        self.consume_query_type = canmessage.QUERY_ALL
        self.consume_query = None

        self.histories = []
        self.subscriptions = []

        self.gridconnect_server = None

        self.in_transition = False
        self.in_learn_mode = False

        self.enumeration_required = False
        self.enumerating = False
        self.enum_start_time = time.ticks_ms()
        self.enum_responses = []
        self.timeout_timer = time.ticks_ms()

        self.num_messages_received = 0
        self.num_messages_sent = 0

        self.callback_flag = asyncio.ThreadSafeFlag()

        self.func_dict = {
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
            cbusdefs.OPC_RSTAT: self.handle_rstat,
        }

    def begin(self, freq=20, max_msgs=1) -> None:
        self.config.begin()
        self.has_ui and self.indicate_mode(self.config.mode)
        self.can.message_received_flag = self.callback_flag
        self.switch.switch_changed_state_flag = self.callback_flag
        self.can.begin()

        asyncio.create_task(self.process(freq, max_msgs))

    def set_switch(self, pin) -> None:
        self.switch = cbusswitch.cbusswitch(pin)
        self.has_ui = True

    def set_leds(self, grn_pin, ylw_pin) -> None:
        self.led_grn = cbusled.cbusled(grn_pin)
        self.led_ylw = cbusled.cbusled(ylw_pin)
        self.has_ui = True

    def set_name(self, name) -> None:
        self.name = bytearray(name)

    def set_params(self, params) -> None:
        self.params = params

    def set_event_handler(self, event_handler) -> None:
        self.event_handler = event_handler

    def set_received_message_handler(self, received_message_handler, opcodes=()) -> None:
        self.received_message_handler = received_message_handler
        self.opcodes = opcodes

    def set_sent_message_handler(self, sent_message_handler) -> None:
        self.sent_message_handler = sent_message_handler

    def send_cbus_message(self, msg) -> None:
        msg.canid = self.config.canid
        msg.make_header()
        self.send_cbus_message_no_header_update(msg)

    def send_cbus_message_no_header_update(self, msg) -> None:
        self.can.send_message__(msg)
        self.has_ui and self.config.mode == MODE_FLIM and self.led_grn.pulse()
        self.num_messages_sent += 1

        if self.sent_message_handler is not None:
            self.sent_message_handler(msg)

        if self.consume_own_messages:
            if msg.matches(self.consume_query_type, self.consume_query):
                self.can.rx_queue.enqueue(msg)

    def set_can(self, can: canio.canio) -> None:
        self.can = can

    def set_config(self, config: cbusconfig.cbusconfig) -> None:
        self.config = config

    async def process(self, freq=50, max_msgs=1) -> None:
        while True:
            await asyncio.sleep_ms(freq)
            # await self.callback_flag.wait()
            # self.logger.log('cbus: callback flag was set')

            if self.in_transition and time.ticks_diff(time.ticks_ms(), self.timeout_timer) >= 30000:
                self.logger.log('cbus: mode change timeout')
                self.in_transition = False
                self.indicate_mode(self.config.mode)
                self.timeout_timer = time.ticks_ms()

            if self.enumeration_required:
                self.logger.log('cbus: enumeration required')
                self.begin_enumeration()

            if self.enumerating and time.ticks_diff(time.ticks_ms(), self.enum_start_time) >= 100:
                self.logger.log('cbus: end of enumeration cycle')
                self.enumerating = False
                self.process_enumeration_responses()
                self.logger.log(f'cbus: canid is now {self.config.canid}')

            if self.has_ui:
                if self.switch.is_pressed() and self.switch.current_state_duration() >= 6000:
                    self.indicate_mode(MODE_CHANGING)

                if self.switch.state_changed and not self.switch.is_pressed():

                    if self.switch.previous_state_duration >= 6000:
                        self.logger.log('cbus: long switch press = change mode')
                        self.in_transition = True

                        if self.config.mode == MODE_SLIM:
                            self.init_flim()
                        elif self.config.mode == MODE_FLIM:
                            self.revert_slim()

                    if 2000 >= self.switch.previous_state_duration >= 1000:
                        self.logger.log('cbus: medium switch press = renegotiate')
                        if self.config.mode == MODE_FLIM:
                            self.in_transition = True
                            self.init_flim()

                    if 1000 >= self.switch.previous_state_duration >= 250:
                        self.logger.log('cbus: short switch press = enumerate')
                        if self.config.canid > 0:
                            self.begin_enumeration()

                    if self.switch.previous_state_duration < 250:
                        self.logger.log('cbus: switch press too short')

                    self.switch.reset()

            if self.poll:
                self.can.poll_for_messages()

            processed_msgs = 0

            while True:
                avail = await self.can.available()

                if avail and processed_msgs < max_msgs:
                    msg = await self.can.get_next_message()

                    if msg:
                        self.num_messages_received += 1

                        for h in self.histories:
                            h.add(msg)

                        for sub in self.subscriptions:
                            sub.publish(msg)

                        if self.gridconnect_server is not None:
                            self.gridconnect_server.output_queue.enqueue(msg)

                        if self.config.mode == MODE_FLIM and self.has_ui:
                            self.led_grn.pulse()

                        if msg.canid & 0x7f == self.config.canid and not self.enumerating:
                            self.logger.log('cbus: can id clash')
                            self.enumeration_required = True

                        if self.received_message_handler is not None:
                            if self.opcodes is not None and len(self.opcodes) > 0 and msg.data[0] in self.opcodes:
                                self.received_message_handler(msg)
                            else:
                                self.received_message_handler(msg)

                        if msg.ext:
                            continue

                        if msg.dlc > 0:
                            try:
                                self.func_dict.get(msg.data[0])(msg)
                            except TypeError:
                                self.logger.log(f'cbus: unhandled opcode = {msg.data[0]:#x}')

                        else:
                            if msg.rtr and not self.enumerating:
                                self.respond_to_enum_request()
                            elif self.enumerating:
                                self.enum_responses[msg.get_canid()] = True

                        processed_msgs += 1

                    else:
                        self.logger.log('cbus: no message found')

                else:
                    # self.logger.log(f'cbus: end of data, avail = {avail}, msgs = {processed_msgs}')
                    break

            # self.logger.log('cbus: end of process')

        #
        # end of process()
        #

    def handle_accessory_event(self, msg: canmessage.canmessage) -> None:
        if self.event_handler is not None:
            node_number, event_number = msg.get_node_and_event_numbers()
            idx = self.config.find_existing_event(node_number, event_number)

            if idx >= 0:
                self.event_handler(msg, idx)

    def handle_rqnp(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('RQNP')

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

    def handle_rqnpn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('RQNPN')

        if msg.get_node_number() == self.config.node_number:
            paran = msg.data[3]

            if paran <= self.params[0] and paran < len(self.params):
                omsg = canmessage.canmessage(self.config.canid, 5)
                omsg.data[0] = cbusdefs.OPC_PARAN
                omsg.data[1] = int(self.config.node_number >> 8)
                omsg.data[2] = self.config.node_number & 0xff
                omsg.data[3] = paran
                omsg.data[4] = self.params[paran]
                self.send_cbus_message(omsg)
            else:
                self.send_CMDERR(9)

    def handle_snn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('SNN')

        if self.in_transition:
            self.config.set_node_number(msg.get_node_number())
            self.send_nn_ack()

            self.in_transition = False
            self.config.set_mode(MODE_FLIM)
            self.indicate_mode(MODE_FLIM)
            self.enumeration_required = True

    def handle_canid(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('CANID')

        if msg.get_node_number() == self.config.node_number:
            if msg.data[3] < 1 or msg.data[3] > 99:
                self.send_CMDERR(7)
            else:
                self.config.set_canid(msg.data[3])
                self.send_nn_ack()

    def handle_enum(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('ENUM')

        if (msg.get_node_number() == self.config.node_number
                and msg.get_canid() != self.config.canid
                and not self.enumerating):
            self.begin_enumeration()

    def handle_nvrd(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NVRD')

        if msg.get_node_number() == self.config.node_number:
            if msg.data[3] > self.config.num_nvs:
                self.send_CMDERR(0)
            else:
                omsg = canmessage.canmessage(self.config.canid, 5)
                omsg.data[0] = cbusdefs.OPC_NVANS
                omsg.data[1] = int(self.config.node_number >> 8)
                omsg.data[2] = self.config.node_number & 0xff
                omsg.data[3] = msg.data[3]
                omsg.data[4] = self.config.read_nv(msg.data[3])
                self.send_cbus_message(omsg)

    def handle_nvset(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NVSET')

        if msg.get_node_number() == self.config.node_number:
            if msg.data[3] > self.config.num_nvs:
                self.send_CMDERR(0)
            else:
                self.config.write_nv(msg.data[3], msg.data[4])
                self.send_WRACK()

    def handle_nnlrn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NNLRN')

        if msg.get_node_number() == self.config.node_number:
            self.in_learn_mode = True
            self.params[8] = self.params[8] | 1 << 5

    def handle_nnuln(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NNULN')

        if msg.get_node_number() == self.config.node_number:
            self.in_learn_mode = False
            self.params[8] = self.params[8] % 1 << 5

    def handle_rqevn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('RQEVN')

        if msg.get_node_number() == self.config.node_number:
            num_events = self.config.count_events()
            omsg = canmessage.canmessage(self.config.canid, 4)
            omsg.data[0] = cbusdefs.OPC_NUMEV
            omsg.data[1] = int(self.config.node_number >> 8)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = num_events
            self.send_cbus_message(omsg)

    def handle_nerd(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NERD')

        if msg.get_node_number() == self.config.node_number:
            omsg = canmessage.canmessage(canid=self.config.canid, dlc=8)
            omsg.data[0] = cbusdefs.OPC_ENRSP
            omsg.data[1] = self.config.node_number >> 8
            omsg.data[2] = self.config.node_number & 0xff

            for i in range(self.config.num_events):
                event = self.config.read_event(i)
                if (
                        event[0] == 0xff
                        and event[1] == 0xff
                        and event[2] == 0xff
                        and event[3] == 0xff
                ):
                    pass
                else:
                    omsg.data[3] = event[0]
                    omsg.data[4] = event[1]
                    omsg.data[5] = event[2]
                    omsg.data[6] = event[3]
                    omsg.data[7] = i
                    self.send_cbus_message(omsg)
                    time.sleep_ms(10)

    def handle_reval(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('REVAL')

        if msg.get_node_number() == self.config.node_number:
            omsg = canmessage.canmessage(canid=self.config.canid, dlc=6)
            omsg.data[0] = cbusdefs.OPC_NEVAL
            omsg.data[1] = int(self.config.node_number >> 8)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = msg.data[3]
            omsg.data[4] = msg.data[4]
            omsg.data[5] = self.config.read_event_ev(msg.data[3], msg.data[4])
            self.send_cbus_message(omsg)

    def handle_nnclr(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NNCLR')

        if (
                msg.get_node_number() == self.config.node_number
                and self.in_learn_mode
        ):
            self.config.clear_all_events()
            self.send_WRACK()

    def handle_nnevn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('NNEVN')

        if msg.get_node_number() == self.config.node_number:
            omsg = canmessage.canmessage(self.config.canid, 4)
            omsg.data[0] = cbusdefs.OPC_EVNLF
            omsg.data[1] = int(self.config.node_number >> 8)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = self.config.num_events - self.config.count_events()
            self.send_cbus_message(omsg)

    def handle_qnn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('QNN')

        if self.config.node_number > 0:
            omsg = canmessage.canmessage(self.config.canid, 6)
            omsg.data[0] = cbusdefs.OPC_PNN
            omsg.data[1] = int(self.config.node_number >> 8)
            omsg.data[2] = self.config.node_number & 0xff
            omsg.data[3] = self.params[1]
            omsg.data[4] = self.params[3]
            omsg.data[5] = self.params[8]
            self.send_cbus_message(omsg)

    def handle_rqmn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('RQMN')

        if self.in_transition:
            omsg = canmessage.canmessage(self.config.canid, 8)
            omsg.data[0] = cbusdefs.OPC_NAME

            for i, c in enumerate(self.name):
                omsg.data[i + 1] = c

            self.send_cbus_message(omsg)

    def handle_evlrn(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('EVLRN')

        if self.in_learn_mode:
            if self.config.write_event(
                    msg.get_node_number(),
                    msg.get_event_number(),
                    msg.data[5],
                    msg.data[6],
            ):
                self.send_WRACK()
            else:
                self.send_CMDERR(10)

    def handle_evuln(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('EVULN')

        if self.in_learn_mode:
            if self.config.clear_event(
                    msg.get_node_number(),
                    msg.get_event_number(),
            ):
                self.send_WRACK()
            else:
                self.send_CMDERR(10)

    def handle_dtxc(self, msg: canmessage.canmessage) -> None:
        # self.logger.log('DTXC')
        if self.long_message_handler is not None:
            self.long_message_handler.handle_long_message_fragment(msg)

    def handle_rstat(self, msg: canmessage.canmessage) -> None:
        self.logger.log('cbus: no action for OPC_RSTAT')

    def send_nn_ack(self) -> None:
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_NNACK
        omsg.data[1] = int(self.config.node_number >> 8)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

    def send_WRACK(self) -> None:
        # self.logger.log('send_WRACK')
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_WRACK
        omsg.data[1] = int(self.config.node_number >> 8)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

    def send_CMDERR(self, errno: int) -> None:
        # self.logger.log('send_CMDERR')
        omsg = canmessage.canmessage(self.config.canid, 4)
        omsg.data[0] = cbusdefs.OPC_WRACK
        omsg.data[1] = int(self.config.node_number >> 8)
        omsg.data[2] = self.config.node_number & 0xff
        omsg.data[3] = errno & 0xff
        self.send_cbus_message(omsg)

    def begin_enumeration(self) -> None:
        self.enumeration_required = False
        if self.config.mode == MODE_FLIM:
            omsg = canmessage.canmessage(self.config.canid, 0, rtr=True)
            self.enum_responses = [False] * 128
            self.enumerating = True
            self.send_cbus_message(omsg)
            self.enum_start_time = time.ticks_ms()
        else:
            self.logger.log('cbus: no enumeration if SLiM')

    def process_enumeration_responses(self) -> None:
        self.enum_start_time = 0
        self.enumerating = False
        new_id = self.config.canid

        if True not in self.enum_responses:
            self.logger.log('cbus: no enumeration responses received')

        for i, r in enumerate(self.enum_responses, start=1):
            if not r:
                new_id = i
                break

        if new_id > 0:
            self.logger.log(f'cbus: took unused can id = {new_id}')
            self.config.set_canid(new_id)
            self.send_nn_ack()
        else:
            self.send_CMDERR(7)

    def respond_to_enum_request(self) -> None:
        omsg = canmessage.canmessage(self.config.canid, 0)
        self.send_cbus_message(omsg)

    def init_flim(self) -> None:
        self.indicate_mode(MODE_CHANGING)
        self.in_transition = True
        self.timeout_timer = time.ticks_ms()

        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_RQNN
        omsg.data[1] = int(self.config.node_number >> 8)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

    def revert_slim(self) -> None:
        omsg = canmessage.canmessage(self.config.canid, 3)
        omsg.data[0] = cbusdefs.OPC_NNREL
        omsg.data[1] = int(self.config.node_number >> 8)
        omsg.data[2] = self.config.node_number & 0xff
        self.send_cbus_message(omsg)

        self.in_transition = False
        self.config.set_mode(MODE_SLIM)
        self.config.set_canid(0)
        self.config.set_node_number(0)
        self.indicate_mode(MODE_SLIM)

    def indicate_mode(self, mode: int) -> None:
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

    def set_long_message_handler(self, handler) -> None:
        self.long_message_handler = handler

    def set_gcserver(self, server: gcserver.gcserver) -> None:
        self.gridconnect_server = server

    def add_history(self, history) -> None:
        # self.logger.log(f'cbus: add history, query type = {history.query_type}, query = {history.query}')
        self.histories.append(history)

    def remove_history(self, history: cbushistory.cbushistory) -> None:
        for i, h in enumerate(self.histories):
            if h.id == history.id:
                del self.histories[i]

    def add_subscription(self, sub: cbuspubsub.subscription) -> None:
        # self.logger.log(
        #     f'cbus: add subscription, name = {sub.name}, id = {sub.id}, query type = {sub.query_type}, query = {sub.query}')
        self.subscriptions.append(sub)

    def remove_subscription(self, sub: cbuspubsub.subscription) -> None:
        # self.logger.log(f'cbus: remove subscription, id = {sub.id}')
        for i, s in enumerate(self.subscriptions):
            if s.id == sub.id:
                del self.subscriptions[i]
                break
