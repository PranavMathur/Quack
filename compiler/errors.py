#raised by the compiler when code is not legal
class CompileError(Exception):
    def __init__(self, msg, meta=None):
        super().__init__(msg)
        self.meta = meta
