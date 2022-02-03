from functools import reduce
import hashlib
import re

class IntegerOverflow(Exception):
    pass

class CellOverflow(Exception):
    pass

class CellUnderflow(Exception):
    pass

def bits_to_uint(bits):
    return reduce(lambda a, b: 2*a + b, bits, 0)
def bits_to_int(bits):
    x = bits_to_uint(bits)
    b = (1 << (len(bits) - 1))
    if x >= b:
        x -= b * 2
    return x


# ordinary cells only
class Cell:
    def __init__(self):
        self.bits = []
        self.refs = []
        self.depth = 0

    def hash(self):
        repr = bytearray()
        r = len(self.refs)
        s = 0
        l = 0
        d1 = r + 8 * s + 32 * l
        b = len(self.bits)
        d2 = b // 8 + (b + 7) // 8
        repr.append(d1)
        repr.append(d2)

        # padding
        resd = b % 8
        if resd > 0:
            self.bits.append(1)
            for _ in range(7 - resd):
                self.bits.append(0)

        for i in range((b + 7) // 8):
            octet = self.bits[8 * i : 8 * (i + 1)]
            byte = bits_to_uint(octet)
            repr.append(byte)

        for ref in self.refs:
            repr += ref.depth.to_bytes(2, byteorder='big')

        for ref in self.refs:
            h = int(ref.hash(), 16)
            repr += h.to_bytes(32, byteorder='big')

        return hashlib.sha256(repr).hexdigest()

    def begin_parse(self):
        res = Slice()
        res.bits = self.bits
        res.refs = self.refs
        return res

class Builder:
    def __init__(self):
        self.bits = []
        self.refs = []

    def _check_size(func):
        def wrapper(self, *args):
            func(self, *args)
            if len(self.bits) > 1023:
                raise CellOverflow()
            if len(self.refs) > 4:
                raise CellOverflow()
        return wrapper

    @_check_size
    def _store_integer(self, x, len):
        x_bits = [(x >> i) & 1 for i in range(len)]
        x_bits.reverse()
        self.bits += x_bits

    def store_uint(self, x, len):
        if x < 0 or x >= (1 << len):
            raise IntegerOverflow()
        self._store_integer(x, len)

    def store_int(self, x, len):
        m = (1 << (len - 1))
        if x < -m or x >= m:
            raise IntegerOverflow()
        self._store_integer(x, len)

    def store_grams(self, x):
        if x < 0:
            raise IntegerOverflow()
        len = next(filter(lambda l: x < (1 << l), [i * 8 for i in range(16)]), None)
        self.store_uint(len // 8, 4)
        self.store_uint(x, len)

    @_check_size
    def store_slice(self, s):
        self.bits += s.get_bits()
        self.refs += s.get_refs()

    @_check_size
    def store_ref(self, c):
        self.refs.append(c)

    def end_cell(self):
        res = Cell()
        res.bits = self.bits.copy()
        res.refs = self.refs.copy()
        res.depth = 0
        if len(res.refs) > 0:
            res.depth = 1 + max(map(lambda x: x.depth, res.refs))
        return res

class Slice:
    def __init__(self, literal=None):
        self.refs = []
        self.bpos = 0
        self.rpos = 0
        if literal is None:
            self.bits = []
        elif re.match(r"b{[01]*}", literal):
            self.bits = list(map(int, literal[2:-1]))
        elif re.match(r"x{[0-9a-f]*}", literal):
            gs = map(lambda x: int(x, 16), literal[2:-1])
            gs = map(lambda x: [(x >> 3) & 1, (x >> 2) & 1, (x >> 1) & 1, x & 1], gs)
            self.bits = sum(gs, [])
        else:
            raise ValueError('Slice initialization exception, unknown literal: ', literal)

    def bitlen(self):
        return len(self.bits) - self.bpos
    def reflen(self):
        return len(self.refs) - self.rpos
    def get_bits(self):
        return self.bits[self.bpos:]
    def get_refs(self):
        return self.refs[self.rpos:]

    def load_uint(self, lenght):
        res = self.preload_uint(lenght)
        self.bpos += lenght
        return res

    def preload_uint(self, lenght):
        if self.bpos + lenght > len(self.bits):
            raise CellUnderflow()
        s = self.bits[self.bpos:self.bpos + lenght]
        return bits_to_uint(s)

    def load_int(self, lenght):
        res = self.preload_int(lenght)
        self.bpos += lenght
        return res

    def preload_int(self, lenght):
        if self.bpos + lenght > len(self.bits):
            raise CellUnderflow()
        s = self.bits[self.bpos:self.bpos + lenght]
        return bits_to_int(s)

    def load_grams(self):
        lenght = self.load_uint(4)
        amount = self.load_uint(lenght * 8)
        return amount

    def load_ref(self):
        if self.rpos + 1 > len(self.refs):
            raise CellUnderflow()
        res = self.refs[self.rpos]
        self.rpos += 1
        return res

    def hash(self):
        b = Builder()
        b.store_slice(self)
        return b.end_cell().hash()
