# Semantic representation of hardware registers and structs

A base library to describe hard-spec'ed binary structures and registers. Think of
binary blobs that have rigid struct (offsets, representation), hardware registers
that come from the chips. Goal is to abstract these positions into the semantic
names of bits and bytes.

Definitions written using this library should be as easy as following the datasheet/spec.
No frills, no syntactic sugar. Then, you should be able to write decoders (+encoders?)
just using semantic names.


## Examples

Definition of some protocol:

```
class CPER_valid_bits(HwRegister):
    platform_id = HwBits(0)
    timestamp = HwBits(1)
    partition_id = HwBits(2)

class CPER(DataStruct):
    head = Static(0, b"CPER")
    revision = UShort(4)
    head_end = StaticUL(6, 0xFFFFFFFF)
    section_count = UShort(10)
    error_severity = ULong(12)
    valid_bits = Reg(16, 4, CPER_valid_bits)

    platform_id = GUID(32)  # overlaps and gaps allowed!

```

Using it:

```
    with open('error-20231102.bin', 'rb') as fp:
        cper_rec = CPER(fp)

    if cper_rec.valid_bits.platform_id:
        print(f"Platform ID: {cper_rec.platform_id}")
```


## Requirements

hwbits_lib is solely based on Python standard libraries (3.10+ recommended),
no external dependencies.


## Full documentation
...

See the [CONTRIBUTING](CONTRIBUTING.md) file for how to help out.

## License
hwbits_lib is MIT-licensed, as found in the LICENSE file.
