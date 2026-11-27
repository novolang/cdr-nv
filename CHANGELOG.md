# Changelog

All notable changes to cdr-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

## 0.1.2 — 2026-11-27

### Changed

- The README program drops the `Result` of `push_str` with `let _ =` and a comment that says why: the text fits the 64 bytes the field holds.  The binding that no line read is gone.  No signature of the package changed.

## 0.1.1 — 2026-11-19

### Added

- `scripts/rclpy_vectors.py`, `tests/jazzy_vectors.tsv` and
  `tests/jazzy_vectors_<package>_tests.nv`: 168 vectors from the ROS 2 Jazzy
  middleware. The script builds one instance of every bundled message and of
  every service request and response (104 types) with each field set to a
  value other than its default, has `rclpy.serialization.serialize_message`
  serialise it, and writes the values into the tests and the bytes into the
  TSV. For each of the 64 types that has a string or a sequence it also builds
  an instance in which each is as long as the generated field holds. A test
  builds the message from the values and compares its encoding with the
  middleware's bytes, decodes the middleware's bytes and checks every field,
  encodes the result again, and sends it through the other byte order and
  back. The TSV is checked in, so the tests need no ROS 2.
- `examples/ros2_interop/`: a program that encodes a `std_msgs/Int32` and a
  `geometry_msgs/Twist` with this package and publishes them through ros2-nv
  0.1.1's session to a Micro XRCE-DDS Agent over TCP, where `ros2 topic echo`
  prints them. It is a package of its own, so this package's
  `[dependencies]` stays empty. `docs/ros2-interop.md` has the commands and a
  run.

### Fixed

- The README said that nothing pads the end of a message and that an empty
  message is one byte, and did not say that the middleware's serialiser pads a
  payload of fewer than four bytes to four. The 104 types were compared with
  the middleware's bytes and none differed in a field, a length or an
  alignment; the one difference is those trailing zero bytes (a
  `std_msgs/Int8` is eight bytes with its header from the middleware and five
  from this package, and both read back). Rules 4 and 13 now say so.
- `tests/msggen_tests.nv` carried a `workaround` tag for a language bug that
  is closed since; the helper it excused is written the plain way, and the
  shard audit's `workaround-stale` row passes.

## 0.1.0 — 2026-11-10

The first release.

### Added

- `cdr`: Common Data Representation version 1 as ROS 2 messages travel in
  it. A `Writer` and a `Reader` over fixed-capacity buffers (`CDR_CAP`, 1,024
  bytes, the header included) that allocate nothing; little-endian and
  big-endian headers; `bool`, the integer widths, `float32` and `float64`,
  strings, sequence counts and the alignment of each, counted from the end of
  the header. A failure is recorded in a sticky `Status` and the first one is
  the one reported.
- `cdrbytes`: the writer's bytes as a `Bytes`, and a reader over a `Bytes`.
  A host module.
- `msggen`: a parser for `.msg` and `.srv` definitions (primitives, bounded
  strings, fixed, bounded and unbounded arrays, nested messages, constants
  and defaults) and a generator that writes one module per ROS package, with
  a struct per message that has `new`, `sample`, `encode`, `decode`,
  `decode_into`, the ROS 2 and DDS type names and the type hash. A host
  module, with a program in `examples/msggen_cli.nv`.
- The bundled sets, as modules in `src/`: `builtin_interfaces`, `std_msgs`,
  `geometry_msgs`, `rcl_interfaces`, `std_srvs`, `service_msgs` and a subset
  of `sensor_msgs`, each with its definitions in `src/interfaces/`. The
  definitions are the files of the ROS 2 Jazzy distribution (std_msgs 5.3.8),
  copied from `/opt/ros/jazzy/share`. The set first written from memory
  differed from it in one file, `sensor_msgs/NavSatStatus.msg`, which lacked
  `STATUS_UNKNOWN`, `SERVICE_UNKNOWN` and the default of `status`, and in
  omitting four `geometry_msgs` messages and most of `rcl_interfaces`; the
  distribution's files replace it.
- The type hash, `RIHS01_` and 64 digits, of every message and of every
  service, computed by `msggen.type_hash` and `msggen.service_type_hash` and
  emitted as `type_hash()`, `service_type_name()` and `service_type_hash()`.
  `tests/hashes_tests.nv` compares all 115 with the distribution's own.
- `tests/embedded_probe.nv`: a firmware program that builds for the
  `nrf52-qemu` board with its checks under `@no_alloc`.
- Test vectors derived by hand, and one captured vector, a
  `tf2_msgs/TFMessage` from the foxglove/cdr repository's tests.

### Named as decided

**`decode` answers an optional value, not a `Result`.** A `Result` that
carries a value is a heap cell at the embedded tier, so a message's `decode`
answers `?T` and the reader's `result()` says why it is `None`.
`decode_into` answers the status.

**A struct named for a type the language has takes `Msg` after its name**,
because the compiler refuses a struct with the name of a standard-library
type (E2000), and a struct named `Bool` or `String` also changes what the
type means in every other module of the program.

This release requires novo 0.23.0 or later.
