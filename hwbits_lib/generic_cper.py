# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Parser of Common Platform Error Record (CPER)
"""

import time

from .hwstructs import (
    DataStruct,
    GUID,
    MultiSectionsVar,
    Nested,
    ParentBody,
    Reg,
    Static,
    Text,
    UChar,
)
from .little_endian import DynSizeUL, StaticUL, ULong, ULong64, UShort
from .registers import HwBits, HwRegister

# fmt: off
class CPER_valid_bits(HwRegister):
    platform_id = HwBits(0)
    timestamp = HwBits(1)
    partition_id = HwBits(2)


class CPER_flags(HwRegister):
    recovered = HwBits(0)
    preverr = HwBits(1, doc="Qualifies an error condition as one "
                            "that occurred during a previous session.")
    simulated = HwBits(2, doc="Intentionally simulated/injected")


class CPER_section_descr(DataStruct):
    _name_var = "section_type"

    offset = ULong(0)
    length = ULong(4)
    revision = UShort(8)

    section_type = GUID(16)
    FRU_id = GUID(32)
    severity = ULong(48)
    FRU_text = Text(52, 20)

    body = ParentBody("offset", "length")


class CPER_tstamp_bits(HwRegister):
    precise = HwBits(0)


class CPER_timestamp(DataStruct):
    seconds = UChar(0)
    minutes = UChar(1)
    hours = UChar(2)
    flags = Reg(3, 1, CPER_tstamp_bits)
    day = UChar(4)
    month = UChar(5)
    year = UChar(6)
    century = UChar(7)

    def __str__(self):
        return f"{self.century-1}{self.year:02d}-{self.month:02d}-{self.day:02d} "\
                f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"

    @property
    def datetime(self) -> int:
        return self.__int__()

    def __int__(self):
        year = (self.century -1) * 100 + self.year
        ts = time.mktime((year, self.month, self.day,
                            self.hours, self.minutes, self.seconds,
                            -1, -1, -1))
        return int(ts)

class CPER(DataStruct):
    _name_var = "notification_type"

    head = Static(0, b"CPER")
    revision = UShort(4)
    head_end = StaticUL(6, 0xFFFFFFFF)
    section_count = UShort(10)
    error_severity = ULong(12)
    valid_bits = Reg(16, 4, CPER_valid_bits)

    rec_length = DynSizeUL(20)

    timestamp = Nested(24, CPER_timestamp)
    platform_id = GUID(32)
    partition_id = GUID(48)
    creator_id = GUID(64)
    notification_type = GUID(80)

    record_id = ULong64(96)
    flags = Reg(104, 4, CPER_flags)

    sections = MultiSectionsVar(128, "section_count", CPER_section_descr)
