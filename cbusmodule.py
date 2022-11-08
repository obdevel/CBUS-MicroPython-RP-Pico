# module.py
# cbus application base class

import logger


class cbusmodule:
    def __init__(self):
        self.logger = logger.logger()
        # self.logger.log("cbusmodule constructor")

        self.lm = None
        self.history = None
        self.start_gc_server = False

    def initialise(self):
        pass

    def run(self):
        pass

    def event_handler(self, msg, idx):
        self.logger.log(f"-- user event handler: idx = {idx}")
        self.logger.log(msg)

    def frame_handler(self, msg):
        self.logger.log("-- user frame handler:")
        self.logger.log(msg)

    def long_message_handler(self, message, streamid, status):
        self.logger.log("-- user long message handler:")
        self.logger.log(f"status = {status}, streamid = {streamid}, msg = <{message}>")

