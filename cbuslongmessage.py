
# cbuslongmessage.py

import cbus

class receive_context:

    def __init__(self):
        self.state = False
        self.canid = 0
        self.buffer = bytearray()
        self.last_fragment_received = 0

class transmit_context:

    def __init__(self):
        self.state = False
        self.buffer = None
        self.last_fragment_sent = 0

class cbuslongmessage:

    def __init__(self, cbus):

        print('** long message constructor')
        self.cbus = cbus

        if not isinstance(bus, cbus.cbus):
            raise TypeError('bus is not an instance of class cbus')

        self.ids = None
        self.cbus.set_long_message_handler(self)
        self.user_handler = None
        self.receive_contexts = [receive_context()] * 4
        self.transmit_contexts = [transmit_context()] * 4

    def subscribe(self, ids, handler):
        print('subscribe')
        self.ids = ids
        self.user_handler = handler
        print(ids)
        print(handler)

    def handle_Long_message_fragment(self, msg):
        print('handling fragment')

    def send_long_message(self, msg):
        print('sending long message')

    def process(self):
        pass
