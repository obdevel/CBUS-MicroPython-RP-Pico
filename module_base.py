# module.py
# cbus application base class

class module_base():
    
    def __init__(self):
        # print('** module_base constructor')
        pass

    def initialise(self):
        pass

    def run_cbus_loop(self):
        pass

    def run(self):
        pass

    def frame_handler(self, msg):
        print('-- user frame handler:')
        print(msg)

    def long_message_handler(self, message, streamid, status):
        print(f'-- user long message handler: status = {status}, streamid = {streamid}, msg = |{message}|')
        print()

    def flim(self):
        self.cbus.config.set_mode(1)
        self.cbus.config.set_canid(5)
        self.cbus.config.set_node_number(333)
        self.cbus.config.reboot()

