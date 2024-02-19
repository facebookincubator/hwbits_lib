# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.


"""Definitions of hardware reginster classes
"""

from __future__ import annotations

from typing import Optional


# fmt: off
class HwBits:
    """Descriptor for bitfields inside a `HwRegister` class

        Use like::

            class BDFL_reg(HwRegister):
                active = HwBits(7, doc="Is active")

            a = BDFL_reg(b'10001010')
            assert a.active

            a.active = 0
            print(a)

    """
    def __init__(self, start: int, stop: Optional[int] = None, doc: str = ""):
        self.offset = start
        if stop is None:
            self.bitmask = 0x01
        else:
            if stop < start:
                raise TypeError("bit stop must be greater than start")
            self.bitmask = 2 ** (stop - start + 1) - 1
        self.__doc__ = doc

    def __get__(self, reg, owner=None):
        return (reg.value >> self.offset) & self.bitmask

    def __set__(self, reg, value):
        if not isinstance(value, int):
            raise TypeError("value must be integer")

        reg.value = ((reg.value & ~(self.bitmask << self.offset))
                     | ((value & self.bitmask) << self.offset))
        return value

    def __delete__(self, reg):
        reg.value &= self.bitmask << self.offset


class HwRegister:
    """Representation of a hardware register

        On a class level, this will have convenience methods for accessing
        the bits of the register

        As a container, it only holds the bits themselves (in `value`),
        but class-level descriptors can extract individual bits (or ranges)
        into virtual attributes (with no extra storage).

        Also supports item operator to get arbitrary bits::

            a = register[16:23]  # get third byte of value


        Note: data arrives LSB first (Intel order) !
    """
    __slots__ = ('value',)

    def __init__(self, value: int):
        self.value = value

    def copy(self):
        return self.__class__(self.value)

    @classmethod
    def from_bytes_lsb(cls, data: bytes) -> HwRegister:
        val = 0
        for i, d in enumerate(data):
            val |= d << 8 * i
        return cls(val)

    def __repr__(self):
        return f"<{self.__class__.__name__} 0x{self.value:x}>"

    def __str__(self):
        return f"0x{self.value:x}"

    def __eq__(self, other):
        return other.__class__ is self.__class__ \
            and other.value == self.value

    def __getitem__(self, part) -> int:
        """Retrieve one or more bits of the register
        """
        if isinstance(part, int):
            return (self.value >> part) & 0x01

        if isinstance(part, slice):
            if part.start is None or part.step is not None:
                raise TypeError("register indices must be two-part slices")
            if part.stop <= part.start:
                raise IndexError("bit length must be positive")

            return (self.value >> part.start) & (2 ** (part.stop - part.start + 1) - 1)

        raise TypeError("register indices must be integers")
