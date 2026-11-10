#!/usr/bin/env bash
# scripts/regen.sh — write src/<package>.nv again from the
# definitions beside it (the .msg and .srv files under src/interfaces/).
#
#   bash scripts/regen.sh            # every bundled package
#   bash scripts/regen.sh std_msgs   # one
#
# Each package's definitions are the .msg and .srv files under
# src/interfaces/<package>/.  msggen orders them by file name itself,
# and writes the package's round-trip tests, tests/gen_<package>_tests.nv,
# beside the module.
#
# `cdr_test_msgs` is not a ROS package.  It is a fixture: one message with
# a field of every primitive, one with every shape a field can take, and
# an empty one, so that the generator's output for the rare shapes is
# compiled and round-tripped like the rest.
# `tests/interfaces_current_tests.nv` asserts that what this writes is
# what is committed, so a change to msggen or to a definition that is
# not followed by this script fails the suite.
#
# The generator is built from a copy of its three sources in a scratch
# directory, because a package build compiles every module under src/,
# and a generated module that no longer compiles would then stop the
# program that regenerates it.
set -eu
cd "$(dirname "$0")/.."
NOVO="${NOVO:-novo}"
pkgs="${*:-builtin_interfaces std_msgs geometry_msgs sensor_msgs rcl_interfaces std_srvs service_msgs cdr_test_msgs}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp examples/msggen_cli.nv "$work"/main.nv
cp src/msggen.nv src/cdr.nv "$work"/
(cd "$work" && "$NOVO" build main.nv -o "$work/msggen" >/dev/null)
for pkg in $pkgs; do
  files=$(ls src/interfaces/"$pkg"/*/*.msg src/interfaces/"$pkg"/*/*.srv 2>/dev/null || true)
  # rcl_interfaces nests its messages (a ParameterEvent holds three lists of
  # Parameters, each holding a ParameterValue with a list of strings), which
  # multiplies the capacities: at 64 and 16 one ParameterEvent is 80 KB and
  # the compiler needs over an hour for the module.  Smaller capacities keep
  # it to a few kilobytes.
  caps="--string-cap 64 --seq-cap 16"
  if [ "$pkg" = rcl_interfaces ]; then caps="--string-cap 32 --seq-cap 4"; fi
  # shellcheck disable=SC2086
  "$work/msggen" --package "$pkg" --out "src/$pkg.nv" --tests "tests/gen_${pkg}_tests.nv" --include src/interfaces $caps $files
  echo "src/$pkg.nv tests/gen_${pkg}_tests.nv"
done
