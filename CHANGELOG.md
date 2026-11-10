# Changelog

All notable changes to cdr-nv are recorded here. The format is
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 rule that a breaking change bumps the MINOR number.

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
