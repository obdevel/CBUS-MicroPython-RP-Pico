# module.py
# cbus application base class

import logger


class cbusmodule:
    def __init__(self):
        self.logger = logger.logger()
        self.logger.log("cbusmodule constructor")
        pass

    def initialise(self):
        pass

    def run_cbus_loop(self):
        pass

    def main(self):
        pass

    def event_handler(self, msg, idx):
        self.logger.log(f"-- user event handler: idx = {idx}")
        self.logger.log(msg)

    def frame_handler(self, msg):
        self.logger.log("-- user frame handler:")
        self.logger.log(msg)

    def long_message_handler(self, message, streamid, status):
        self.logger.log(
            f"-- user long message handler: status = {status}, streamid = {streamid}, msg = <{message}>"
        )
        self.logger.log()
