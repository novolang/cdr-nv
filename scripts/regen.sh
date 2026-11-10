#!/usr/bin/env bash
# scripts/regen.sh — write src/interfaces/<package>.nv again from the
# definitions beside it.
#
#   bash scripts/regen.sh            # every bundled package
#   bash scripts/regen.sh std_msgs   # one
#
# Each package's definitions are the .msg and .srv files under
# src/interfaces/<package>/.  msggen orders them by file name itself,
# and writes the package's round-trip tests, tests/gen_<package>_tests.nv,
# beside the module.
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
pkgs="${*:-builtin_interfaces std_msgs geometry_msgs sensor_msgs rcl_interfaces example_interfaces std_srvs}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp src/main.nv src/msggen.nv src/cdr.nv "$work"/
(cd "$work" && "$NOVO" build main.nv -o "$work/msggen" >/dev/null)
for pkg in $pkgs; do
  files=$(ls src/interfaces/"$pkg"/*/*.msg src/interfaces/"$pkg"/*/*.srv 2>/dev/null || true)
  # shellcheck disable=SC2086
  "$work/msggen" --package "$pkg" --out "src/interfaces/$pkg.nv" --tests "tests/gen_${pkg}_tests.nv" $files
  echo "src/interfaces/$pkg.nv tests/gen_${pkg}_tests.nv"
done
