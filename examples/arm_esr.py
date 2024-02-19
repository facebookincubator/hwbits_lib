# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

""" This code is EXPERIMENTAL, by any means not complete against the spec!
"""

from __future__ import annotations

from typing import Dict, Tuple, Type

from hwbits_lib.registers import HwBits, HwRegister


class ISS_reg_base(HwRegister):
    """Base class for ISS sub registers"""

ARM_EC_VALUES: Dict[int, Tuple[Type[ISS_reg_base], str]] = {}

class ARM_ESR(HWRegister):
    ess2 = HwBits(32, 36)
    ec = HwBits(26, 31, "Exception class")
    il = HwBits(25, doc="Instruction Length")
    iss_bits = HwBits(0, 24, "raw bits of ISS")

    @property
    def iss(self):
        """Return a register object for ISS bits"""
        try:
            cls = ARM_EC_VALUES[self.iss_bits][0]
            return cls(self.iss_bits)
        except KeyError:
            # this value not yet implemented
            return ISS_reg_base(self.iss_bits)


class ISS_unknown(ISS_reg_base):
    res0 = HwBits(0, 24, "All bits reserved")


class ISS_wf_instr(ISS_reg_base):
    TL_VALUES = {
        0b00: "WFI",
        0b01: "WFE",
        0b10: "WFIT",
        0b11: "WFET",
    }

    cv = HwBits(24, doc="conv field is valid")
    conv = HwBits(20, 23)
    tl_bits = HwBits(0, 1, "Trapped instruction")

    @property
    def tl_str(self):
        return self.TL_VALUES(self.tl_bits)


class ISS_mcr_mrc(ISS_reg_base):
    cv = HwBits(24, doc="conv field is valid")
    conv = HwBits(20, 23)

    Opc2 = HwBits(17, 19)
    Opc1 = HwBits(14, 16)
    CRn = HWBits(10, 13)
    Rt = HwBits(5, 9)
    CRm = HwBits(1, 4)
    direction = HwBits(0)


# ...


ARM_EC_VALUES = {
    0b000000: (ISS_unknown, "Unknown reason"),
    0b000001: (ISS_wf_instr, "Trapped WF* instruction execution"),
    0b000011: (ISS_mcr_mrc, "Trapped MCR or MRC access with (coproc==0b1111) "
                            "that is not reported using EC 0b000000"),
    # ... TODO
}
