# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import struct
import typing
import uuid

from typing import Optional, Tuple, Type


# fmt: off
class DataStructDescr:
    """Any descriptor (direct or indirect) of the DataStruct"""

    def _check(self, name: str, data: DataStruct) -> None:
        """Check if the content is valid, this passes by default"""
        pass

    def __get__(self, data: DataStruct, owner=None):
        raise NotImplementedError(f"base class for {self.__class__.__name__}")

    @property
    def size(self) -> Optional[int]:
        """Return the *minimum* size this member would occupy.

        If variable or not available, use None to indicate that
        """
        return None


class DataStructMember(DataStructDescr):  # pyre-ignore
    """Descriptor baseclass for struct member definitions

    Used for members that occupy fixed space on the struct.
    Most important, each member "knows" its offset on the binary struct
    """

    __slots__: Tuple[str, ...] = ("_offset", )

    _size: int   # needs to be specified per subclass

    def __init__(self, offset: int):
        self._offset = offset

    @property
    def size(self):
        return self._size


class DynSizeBase:
    """Placeholder baseclass for that struct member which conveys dynamic size

    Subclass this to construct short/long/quad integers, little/big endian.
    """


class DataStructMeta(type):
    """Metaclass to construct a DataStruct

    Does the housekeeping of 'preparing' the DataStruct class attributes
    (for subclasses thereof). Also defines their `__slots__` so that all
    DataStruct subclasses are optimized for size.
    """

    def __new__(metacls, name, bases, namespace, **kwds):  # noqa: C901
        """Massage the class definition to count for struct size + extra data slots"""

        if bases:  # subclasses of DataStruct, that is
            slots = []
            for b in bases:
                if sls := getattr(b, '__slots__', None):
                    slots += sls
            min_size = None

            # locate descriptor with highest offset
            cur_dyn = None
            for n, descr in namespace.items():
                if n.startswith("_"):
                    continue
                if not isinstance(descr, DataStructDescr):
                    continue
                dsize = descr.size
                if dsize and hasattr(descr, '_offset'):
                    dsize = descr._offset + dsize
                    if (not min_size) or min_size < dsize:
                        min_size = dsize
                if isinstance(descr, DynSizeBase):
                    if cur_dyn is not None:
                        raise TypeError(f"Duplicate dyn-size definitions: {n} and {cur_dyn}")
                    cur_dyn = n
                if isinstance(descr, DataStructExtraData):
                    slots += descr.init_slots(n)

            namespace['__slots__'] = tuple(slots)
            size = kwds.pop('fixed_size', None)
            if min_size and size is not None:
                if min_size > size:
                    raise TypeError(f"Descriptor size in {name} is greater than "
                                    f"fixed size: {min_size} > {size}")
            elif size is None:
                size = min_size
            namespace['_DataStruct__static_size'] = size
            namespace['_DataStruct__dyn_size_member'] = cur_dyn

        return super().__new__(metacls, name, bases, namespace, **kwds)


class DataStruct(metaclass=DataStructMeta):  # pyre-ignore
    """Base class for well-defined data structs

    Usually, these should have just a bunch of DataStructMember's. Please bear with
    the funny code below, the result is in its usage:

    >>> class MyStruct(DataStruct):
    ...     header = Static(0, b'\x12\x34')
    ...     rec_number = UShort(4)
    ...     payload = HwBytes(6, 12)
    ...     crc = UShort(18)

    >>> s = MyStruct(io.BytesIO(b'\x12\x34\x00\x01...'))
    >>> print(s.header)
    >>> print(s.rec_number)
    """

    __static_size: int
    __dyn_size_member: Optional[str]
    __slots__ = ("_data", )
    _name_var: Optional[str] = None

    @classmethod
    def __iter_members(cls):
        for n, descr in cls.__dict__.items():
            if n.startswith('__'):
                continue
            if isinstance(descr, DataStructDescr):
                yield n, descr

    def __init__(self, buf: typing.BinaryIO):
        if isinstance(buf, memoryview):
            self._data = buf[:self.__static_size]
        else:
            self._data = buf.read(self.__static_size)
        if len(self._data) < self.__static_size:
            raise IOError(5, "Stream data is shorter than struct: "
                            f"{len(self._data)} < {self.__static_size}")

        if self.__dyn_size_member:
            ds = getattr(self, self.__dyn_size_member)
            if ds < self.__static_size:
                raise ValueError("Computed dynamic size is less than static: "
                                 f"{self.__dyn_size_member}={ds} < {self.__static_size}")
            else:
                if isinstance(buf, memoryview):
                    self._data = buf[:ds]
                else:
                    self._data += buf.read(ds - self.__static_size)
                if len(self._data) < ds:
                    raise IOError(5, "Stream data is shorter than expected: "
                                  f"{len(self._data)} < {ds}")

        for name, descr in self.__iter_members():
            descr._check(name, self)
            if isinstance(descr, DataStructExtraData):
                descr._init_extra(self)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, name):
        return self._data[name]

    def __repr__(self):
        return f"<{self.__class__.__name__} len={len(self._data)}>"

    def __str__(self):
        if self._name_var:
            return str(getattr(self, self._name_var))
        return repr(self)


class Static(DataStructMember):
    """Some bytes that are expected to have a fixed value

    Or else struct is corrupt, will fail its `_check()`
    """
    __slots__ = ("_offset", "_size", "_expected")

    def __init__(self, offset:int, expected: bytes):
        self._offset = offset
        self._size = len(expected)
        self._expected = expected

    def __get__(self, data: DataStruct, owner=None):
        if data is None:
            return self
        d = data[self._offset:self._offset + self._size]
        if isinstance(d, memoryview):
            return bytes(d)
        else:
            return d

    def _check(self, name: str, data: DataStruct) -> None:
        val = self.__get__(data)
        if val != self._expected:
            raise ValueError(f"Invalid {name}: {val} != {self._expected}")


class structPoweredMember(type):
    """Metaclass for using `struct` based DataStructMember classes

    This will convert the `_struct_fmt` member to a `_struct = struct.Struct()`
    instance, upon class creation.
    """

    def __new__(metacls, name, bases, namespace, **kwds):
        fmt = namespace.pop('_struct_fmt', None)
        if fmt is not None:
            namespace['_struct'] = struct.Struct(fmt)
            namespace['_size'] = namespace['_struct'].size
        return super().__new__(metacls, name, bases, namespace, **kwds)


class DataStruct2Member(DataStructMember, metaclass=structPoweredMember):  # pyre-ignore
    """Decode some bytes using `struct` module.

    Most useful for standard scalar types, supports endianness specifiers.
    Set this `_struct_fmt` here, metaclass will compile and convert it to
    a `Struct` statically on the class level.
    """
    _struct_fmt: str
    _struct: struct.Struct

    def __get__(self, data: DataStruct, owner=None):
        if data is None:
            return self
        d = data[self._offset:self._offset + self._struct.size]
        return self._struct.unpack(d)[0]


class UChar(DataStruct2Member):
    """Unsigned char"""
    _struct_fmt = "<B"


class HwBytes(DataStructMember):
    """Simple slice of some bytes from the struct"""
    __slots__ = ("_offset", "_size")

    def __init__(self, offset: int, size: int):
        self._offset = offset
        self._size = size

    def __get__(self, data: DataStruct, owner=None):
        if data is None:
            return self

        d = data[self._offset:self._offset + self._size]
        if isinstance(d, memoryview):
            return bytes(d)
        else:
            return d


class GUID(DataStructMember):
    """"GUID/UUID member"""
    _size = 16

    def __get__(self, data: DataStruct, owner=None):
        if data is None:
            return self

        u = data[self._offset:self._offset + 16]
        return uuid.UUID(bytes=bytes(u))


class Text(DataStructMember):
    """Text string, with optional encoding"""
    __slots__ = ("_offset", "_size", "_encoding")

    def __init__(self, offset: int, size: int, encoding:str = 'ascii'):
        self._offset = offset
        self._size = size
        self._encoding = encoding

    def __get__(self, data: DataStruct, owner=None):
        if data is None:
            return self
        t = data[self._offset:self._offset + self._size]
        if isinstance(t, memoryview):
            t = bytes(t)

        # bytes.decode() would preserve the full length of a null-padded string,
        # we have to explicitly reduce that
        n = t.find(b'\x00')
        if n >= 0:
            t = t[:n]
        return t.decode(self._encoding)


class Reg(DataStructMember):
    """Register, mapped to a given register class"""
    __slots__ = ("_offset", "_size", "_reg_cls")

    def __init__(self, offset: int, size: int, reg_cls: Type):
        self._offset = offset
        self._size = size
        self._reg_cls = reg_cls

    def __get__(self,  data: DataStruct, owner=None):
        if data is None:
            return self
        val = data[self._offset:self._offset + self._size]
        return self._reg_cls.from_bytes_lsb(val)


class DataStructExtraData(DataStructDescr):
    """Anything that might need extra data onto the DataStruct"""

    def __init__(self):
        self._name = "_extra"

    def init_slots(self, name: str):
        self._name = name
        return (f"_{name}",)

    def _init_extra(self, data: DataStruct):
        pass

    def _check(self, name: str, data: DataStruct) -> None:
        pass

    def __get__(self,  data: DataStruct, owner=None):
        if data is None:
            return self

        return getattr(data, f"_{self._name}")


class Nested(DataStructExtraData):
    """Nest substruct in this struct"""

    def __init__(self, offset: int, klass: Type[DataStruct]):
        self._offset = offset
        self._klass = klass

    @property
    def size(self):
        return self._klass._DataStruct__static_size

    def _check(self, name: str, data: DataStruct) -> None:
        if len(data) < self._offset + self.size:
            raise IndexError(f"Not enough data for {name}= {self.size}")

    def _init_extra(self, data: DataStruct):
        mv = memoryview(data._data)
        offset = self._offset
        d = self._klass(mv[offset:])  # pyre-ignore
        setattr(data, f"_{self._name}", d)


class MultiSectionsFixed(DataStructExtraData):
    """Defines Nx sections (of some struct) """

    def __init__(self, offset: int, count: int, klass: Type[DataStruct]):
        self._offset = offset
        self._count = count
        if count < 1:
            raise TypeError("Must have at least one fixed section")
        self._klass = klass

    @property
    def size(self):
        return self._count * self._klass._DataStruct__static_size

    def _check(self, name: str, data: DataStruct) -> None:
        if len(data) < self._offset + self.size:
            raise IndexError(f"Not enough data for {name}= {self.size}")

    def _init_extra(self, data: DataStruct):
        mv = memoryview(data._data)
        sections = []
        offset = self._offset
        for _ in range(self._count):
            d = self._klass(mv[offset:])  # pyre-ignore
            offset += len(d)
            sections.append(d)
        setattr(data, f"_{self._name}", sections)


class MultiSectionsVar(DataStructExtraData):
    """Defines Nx sections (of some struct), variable length"""

    def __init__(self, offset: int, count_var: str, klass: Type[DataStruct]):
        self._offset = offset
        self._count_var = count_var
        self._klass = klass

    def _check(self, name: str, data: DataStruct) -> None:
        num_sections = getattr(data, self._count_var)
        if num_sections < 0:
            raise ValueError("Negative section count")
        ksize = self._klass._DataStruct__static_size
        if len(data) < self._offset + (num_sections * ksize):
            raise IndexError(f"Not enough data for {name}= {num_sections} * {ksize}")

    def _init_extra(self, data: DataStruct):
        num_sections = getattr(data, self._count_var)
        mv = memoryview(data._data)
        sections = []
        offset = self._offset
        for _ in range(num_sections):
            d = self._klass(mv[offset:])  # pyre-ignore
            offset += len(d)
            sections.append(d)
        setattr(data, f"_{self._name}", sections)


class ParentBody(DataStructExtraData):
    """Defines a "body" from parent data, indexed by some struct members """

    def __init__(self, offset_var: str, length_var: str):
        self._offset_var = offset_var
        self._length_var = length_var

    def _check(self, name: str, data: DataStruct) -> None:
        offset = getattr(data, self._offset_var)
        length = getattr(data, self._length_var)
        if not isinstance(data._data, memoryview):
            raise TypeError("ParentBody only works in nested structs")
        parent_data = data._data.obj
        if offset + length > len(parent_data):
            raise IndexError(f"Not enough data for {name} at data[{offset} + {length}]")

    def _init_extra(self, data: DataStruct):
        offset = getattr(data, self._offset_var)
        length = getattr(data, self._length_var)
        mv = memoryview(data._data.obj)
        setattr(data, f"_{self._name}", mv[offset:offset+length])
