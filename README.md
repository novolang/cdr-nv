# cdr-nv

[Common Data Representation](https://www.omg.org/spec/CDR/) is the binary
format the Object Management Group's DDS standard uses for data on the
wire. [ROS 2](https://docs.ros.org/) uses it for every message a node
publishes, every request and reply of a service, and every message a
rosbag2 file records. This package writes and reads that format, and
generates novo-lang structs from ROS 2 message definitions that encode
and decode through it.

[ros2-nv](https://novo-lang.org/packages/ros2-nv) is the package that
carries a message to a micro-ROS agent. It holds a message as bytes it does
not read, and this package is the one that reads them.

## What it is

A ROS 2 message on the wire is a four-byte *encapsulation header* followed by
the message's fields, each written at its natural size. The header's first two
bytes name the byte order: `00 01` for little-endian and `00 00` for
big-endian. The last two are options, which this package writes as zero and
does not read.

Every number in the payload is *aligned*: a two-byte integer starts at an
offset that is a multiple of 2, a four-byte one a multiple of 4, an eight-byte
one a multiple of 8, and the gap is filled with zero bytes. The offset is
counted from the first byte after the header. That is the rule of XCDR
version 1, which is what `rosidl_typesupport_fastrtps` writes for every ROS 2
message, and it is the one thing an implementation most often gets wrong:
a `float64` that is the first field of a message sits at byte 4 of the
stream, not byte 8.

A string is a `uint32` length that counts the terminating NUL, then the
characters, then the NUL. A sequence is a `uint32` count and then its
elements. A fixed-length array has no count. A nested message is its fields
in order, with no header and no length of its own.

The package has two parts and a set of modules the second part wrote.

`cdr` is the format itself: a `Writer` and a `Reader`, each holding its bytes
inline in a buffer of `CDR_CAP` bytes (1,024, the header included). Neither
allocates, so the module builds for a microcontroller with no heap allocator.

`msggen` is a generator. It reads a ROS 2 `.msg` or `.srv` definition and
writes a module with one `@value` struct per message. Each struct has `new`,
`encode`, `decode` and `decode_into`, and the ROS 2 type name.

The modules it has already written are bundled:
`builtin_interfaces`, `std_msgs`, `geometry_msgs`, a subset of `sensor_msgs` and
of `rcl_interfaces`, `example_interfaces`'s `AddTwoInts` and `std_srvs`, each
with its definition files in `src/interfaces/`.

**A message that does not fit is a value, not a crash.** A writer whose buffer
is full, a reader that reaches the end of its bytes, a string longer than the
field it is read into and a `bool` byte of 2 are all things a wire does to a
program. Each is recorded in the writer's or the reader's status, and the
status is checked once, at the end.

## Install

```
novo pkg add cdr-nv
```

## Example

The program writes a `std_msgs/String` and reads it back. The bytes are the
ones the rules above give; `tests/vectors_tests.nv` derives them by hand.

```novo
use std.bytes
use cdr
use cdrbytes
use std_msgs

fn main() [io]
    // A message, with its text in the fixed-capacity string the field holds.
    var text: String[64] = String.new()
    let _ = text.push_str("hello")
    let msg = std_msgs.StringMsg { data: text }

    // The writer starts with the four header bytes.  Nothing is allocated:
    // the bytes are inside `w`.
    var w = cdr.writer_le()
    let status = msg.encode(var w)
    println(cdr.status_name(status))                    // success
    println(bytes.to_hex(cdrbytes.to_bytes(w)))         // 000100000600000068656c6c6f00

    // A reader over the same bytes.  `decode` answers None when the bytes
    // are wrong, and the reader says why.
    var r = cdr.reader_from(w.buf)
    match std_msgs.StringMsg.decode(var r)
        Some(back) => println("${back.data.len()} bytes of text")   // 5 bytes of text
        None       => println(cdr.status_name(r.result()))
```

## What the package contains

| Module | Contents |
| --- | --- |
| `cdr` | The `Writer` and the `Reader`, the `Status` they record, and the calls that write and read each primitive, a string and a sequence count. Builds for the embedded tier. |
| `cdrbytes` | The writer's bytes as a `Bytes`, and a reader over a `Bytes`. Host only, because the embedded runtime has no `Bytes`. |
| `msggen` | The definition parser and the module generator, as functions from text to text, and the program's entry `run`. Host only. |
| `builtin_interfaces`, `std_msgs`, `geometry_msgs` | 2, 30 and 29 messages, written from the Jazzy documentation. `geometry_msgs/VelocityStamped` is left out because its field list could not be confirmed. |
| `sensor_msgs`, `rcl_interfaces` | Three messages (`Imu`, `NavSatStatus`, `Temperature`) and five (`FloatingPointRange`, `IntegerRange`, `ParameterDescriptor`, `ParameterType`, `ParameterValue`). They hold the bounded sequences, the constants and the nine-element arrays the tests need. |
| `example_interfaces`, `std_srvs` | One service, `AddTwoInts`, and three, `Empty`, `SetBool` and `Trigger`. Each service is a `...Request` struct and a `...Response` struct. |
| `cdr_test_msgs` | Not a ROS package. Three messages that carry every primitive, every field shape and no field at all, so the generator's rare output is compiled and tested like the rest. |

## How to choose an entry point

**A program on a device uses `cdr` and a generated module.** It declares a
`Writer` or a `Reader` as a local, calls a message's `encode` or `decode`, and
checks the status. Nothing else in the package is needed, and nothing else
builds for a device.

**A program on a workstation adds `cdrbytes`** to move between the buffer and
a `Bytes`: a socket, a file, a recorded message.

**A new set of messages needs `msggen`.** Run it over the definition files of a
ROS package:

```
novo run examples/msggen_cli.nv -- --package my_msgs --out src/my_msgs.nv \
    --string-cap 32 --seq-cap 8 \
    my_msgs/msg/Reading.msg my_msgs/srv/Calibrate.srv
```

`--string-cap` and `--seq-cap` set the size of a string and of a sequence that
the definition leaves unbounded. `--prefix` is the module path the other
packages' modules are found under, empty when they sit beside the generated
one. `--tests FILE` also writes a test module
that round-trips every message. `scripts/regen.sh` runs the generator over every
bundled set.

## The rules a user needs

1. **Alignment is counted from the end of the header.** The first `float64` of
   a message is at stream byte 4. A reader that aligns to the stream's start
   reads every double after it wrong.
2. **A string's length counts its NUL.** `"hello"` is a length of 6. The empty
   string is a length of 1 and one NUL byte, and a length of 0 is refused as
   `BadString`.
3. **A sequence has a count; a fixed array does not.** `float64[3]` is three
   doubles and nothing else. `float64[]` and `float64[<=3]` are a `uint32`
   count and then the doubles.
4. **Nothing pads the end of a message.** A message that ends after a one-byte
   field is that many bytes long, and the length is not rounded up.
5. **The capacity is fixed when the module is generated.** An unbounded string
   holds `--string-cap` bytes (default 64) and an unbounded sequence
   `--seq-cap` elements (default 16). A longer one on the wire is `TooLong`.
   It is never cut short, because a message that decodes to something other
   than what was sent is worse than one that does not decode.
6. **A message is at most `CDR_CAP` bytes (1,024), the header included.** A
   longer one is `Full`. A `sensor_msgs/Image` or a point cloud does not fit.
7. **The first failure is the one reported.** After it, a writer writes
   nothing and a reader answers zero from every call, so a loop bounded by a
   count it read runs no times. Check `result()` once, after the last field.
8. **`decode` answers `None` and the reader says why.** It answers an optional
   value, not a `Result`, because a `Result` that carries a value is a heap cell
   on a device. `decode_into` fills a message in place and answers the status,
   and is the form for a firmware that keeps one message and reuses it.
9. **`uint64` is an `Int` holding the same 64 bits.** The language has no
   unsigned 64-bit type, so a value of 2^63 or more is negative. The bytes on
   the wire are the same.
10. **`float32` is an `fp32`, and the bits are exact.** The writer rounds to
    nearest even, the reader widens exactly, and a NaN, an infinity, a signed
    zero and a subnormal each come back as they went.
11. **Padding is not checked on read.** A writer may put anything in it. A
    `bool` byte other than 0 and 1 is refused, and so is a string whose last
    byte is not NUL.
12. **A struct named for a type the language has gets `Msg` after it.**
    `std_msgs/String` is `std_msgs.StringMsg`, `Bool` is `BoolMsg`, `Char` is
    `CharMsg` and `builtin_interfaces/Duration` is `DurationMsg`. A field named
    for a reserved word gets `_` after it: `type` is `type_`.
13. **An empty message is one byte.** `std_msgs/Empty` has a single `uint8`
    named `structure_needs_at_least_one_member`, because `rosidl` adds one.
14. **`byte`, `char` and `uint8` are all a `u8`.** Each is one byte and none is
    padded.
15. **A service is two structs.** `AddTwoInts.srv` is `AddTwoIntsRequest` and
    `AddTwoIntsResponse`, with the type names
    `example_interfaces/srv/AddTwoInts_Request` and `..._Response`. Each is
    the payload only. Whatever the middleware adds to match a reply to its
    request is not written.

## Running on a microcontroller

`cdr` and every generated message module build for a Cortex-M with no heap
allocator. `tests/embedded_probe.nv` is a firmware program that writes and
reads a `Twist`, a `Header` and an `Imu` in both byte orders, and refuses a
truncated message, a bad `bool` and a full buffer. It is compiled for the
`nrf52-qemu` board as part of this package's checks, so the claim is built and
not asserted. Its checks run under `@no_alloc`, which the build enforces
through every function they call, the standard library's included.

The image is 20,496 bytes of flash, 8,030 of them this package's code, and 520 bytes of static memory. The
build reports 832 bytes of init-time allocation: the two constant results that every `push` on a
fixed-capacity collection answers with, one pair for each element type the
program pushes. No call in the checks allocates after start.

The two other modules are excluded. `cdrbytes` converts to the standard
library's `Bytes`, which the embedded runtime does not define, and `msggen`
builds the text of a module. The manifest names both in `host_modules`, so a
device build leaves them out.

A `Writer` is 1,040 bytes and a `Reader` 1,048, and a message struct is its
fields at their own widths, a `Twist` being 48 bytes and an `Imu` 376. On a
part with 64 KB of RAM, declare one of each and reuse them.

## What is not included

- **`wstring`.** The parser refuses it with a message. Its wire form is not
  one of the vectors this package could be checked against, and almost no
  message uses it.
- **XCDR version 2.** It aligns eight-byte values to four, and adds delimiter
  headers and parameter lists for appendable and mutable types. Messages from
  ROS 2 Jazzy's default middleware are version 1. A header that names version
  2 or a parameter list is refused as `BadHeader`.
- **The type hash.** Iron and later put a SHA-256 over a JSON description of
  the message and of every type in it on the wire, in discovery. The
  description's canonical form has to match the C++ generator's byte for byte,
  and there is no ROS 2 installation on the machine this package was written
  on to compare against. A hash that was never compared is worse than none, so
  it is left out. The type names, `std_msgs/msg/String` and
  `std_msgs::msg::dds_::String_`, are generated.
- **`.action` files.** An action is five topics and two services, and a package
  of its own.
- **A message larger than 1,024 bytes.** See rule 6. The constant is in `cdr.nv`;
  a package that needs a larger buffer vendors the module and changes it, because
  the language cannot make a capacity a parameter of a function.
- **Messages beyond the bundled sets.** The definitions of `sensor_msgs`,
  `nav_msgs`, `tf2_msgs` and the rest are generated with `msggen` from the
  distribution's own files.
- **Bag files.** A bag is a container of CDR messages, and reading one is the
  job of an MCAP reader.

## Related packages

- **ros2-nv** is the ROS 2 node model for a microcontroller. Its `rosmsg` holds
  a serialised message and the header that names its byte order, and a program
  gets the bytes from `cdrbytes.to_bytes` or reads them with
  `cdrbytes.reader_from_bytes`.
- **cbor-nv** and **postcard-nv** are other binary formats for a constrained
  device. CDR is the one DDS and ROS 2 fix, so a node that talks to ROS 2 uses
  this one.
- **cobs-nv** and **crc-nv** frame a message on a serial link.

## Tests

The suite is the files under `tests/`.

`tests/vectors_tests.nv` has ten messages encoded to bytes derived by hand from
the rules, with the derivation above each: `std_msgs/String`, `Int32` in both
byte orders, two `Header`s, a `Twist`, a `sensor_msgs/Imu` after a string that
leaves it three bytes off its boundary, a `ParameterDescriptor` with a bounded
sequence, a sequence of nested floats, and a fixed array after a nested message.
One vector is captured and not derived: the bytes of a `tf2_msgs/TFMessage`
carrying one `TransformStamped`, from `src/CdrWriter.test.ts` in the
[foxglove/cdr](https://github.com/foxglove/cdr) repository. The code here
produces them byte for byte.

`tests/cdr_tests.nv` covers the primitives, both byte orders, the alignment
arithmetic, `float32` patterns including the subnormals, and every status the
writer or the reader can record.

`tests/msggen_tests.nv` feeds the parser single lines and checks each refusal.
`tests/gen_*_tests.nv` are written by the generator: every message of a bundled
set is round-tripped in both byte orders, and the same message with its last
byte cut off must be refused as truncated.
`tests/interfaces_current_tests.nv` generates every bundled module again and
compares it with the file on disk, so a change to the generator or to a
definition that was not followed by `scripts/regen.sh` fails.

`tests/embedded_probe.nv` is the microcontroller program described above.
`tests/coverage.sh` merges the line coverage of the suites over `src/`.

Run the suites with `novo test tests`, and the coverage with
`bash tests/coverage.sh`.

## Licence

Apache-2.0.  See `LICENSE`.
