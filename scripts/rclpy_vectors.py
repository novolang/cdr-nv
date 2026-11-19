#!/usr/bin/env python3
"""scripts/rclpy_vectors.py -- test vectors from the ROS 2 middleware.

For every message and every service half the package bundles, this builds one
deterministic instance with every field set to a value that is not its default
(sequences and strings non-empty, nested messages filled), has the middleware
serialise it, and writes

    tests/jazzy_vectors.tsv                   type, byte order, the values, the hex
    tests/jazzy_vectors_<package>_tests.nv    one test per type, built from the same values

The bytes are `rclpy.serialization.serialize_message`, which calls the
rmw_fastrtps_cpp serialiser, that is Fast CDR, on the instance.  The values go
into the test as literals, so a test builds the message from them, encodes it
and compares the result with the middleware's bytes, then decodes the
middleware's bytes and checks every field against the same values.

Run it where ROS 2 Jazzy is installed, from the package directory:

    bash -c 'source /opt/ros/jazzy/setup.bash && python3 -I scripts/rclpy_vectors.py'

`-I` ignores PYTHONPATH, so the script adds the entries of PYTHONPATH itself.
The tests need ROS 2 for none of this: the TSV is checked in.

Every value is a function of the type's name and the position of the field,
so a second run writes the same files.  The values are chosen to be exact where
a conversion could hide an error: a float32 is a multiple of 1/64 below 2^18,
which float32 holds exactly, and a float64 is printed in the shortest form that
reads back as itself.
"""
import array
import datetime
import importlib
import os
import re
import subprocess
import sys
import zlib

sys.path[:0] = [p for p in os.environ.get("PYTHONPATH", "").split(":") if p]

import rclpy.serialization as ser  # noqa: E402
from rosidl_parser import definition as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
CDR_CAP = 1024

# The packages with bundled definitions, and the capacities scripts/regen.sh
# gives the module of each.
PACKAGES = ["builtin_interfaces", "std_msgs", "geometry_msgs", "sensor_msgs",
            "rcl_interfaces", "std_srvs", "service_msgs"]
CAPS = {"rcl_interfaces": (32, 4)}      # (string cap, sequence cap)
DEFAULT_CAPS = (64, 16)

INT_RANGE = {
    "int8": (-128, 127), "uint8": (0, 255), "octet": (0, 255), "char": (0, 255),
    "int16": (-32768, 32767), "uint16": (0, 65535),
    "int32": (-2147483648, 2147483647), "uint32": (0, 4294967295),
    "int64": (-(2 ** 63) + 1, 2 ** 63 - 1), "uint64": (0, 2 ** 64 - 1),
}
NOVO_INT = {
    "int8": "i8", "uint8": "u8", "octet": "u8", "char": "u8", "int16": "i16",
    "uint16": "u16", "int32": "i32", "uint32": "u32", "int64": "Int", "uint64": "Int",
}

WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
         "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa"]


# ---------------------------------------------------------------------
# The names the generated modules use.

def reserved_types():
    text = open(os.path.join(PKG, "src", "msggen.nv")).read()
    names = set()
    for m in re.finditer(r'^const RESERVED_\d+ = "([^"]*)"', text, re.M):
        names.update(m.group(1).split())
    return names


def reserved_words():
    text = open(os.path.join(PKG, "src", "msggen.nv")).read()
    body = text.split("pub fn field_name", 1)[1].split("\n\n", 1)[0]
    return set(re.findall(r'^\s+"(\w+)"\s+=>\s+"\1_"', body, re.M))


RESERVED_TYPES = reserved_types()
RESERVED_WORDS = reserved_words()


def struct_name(ros):
    return ros + "Msg" if ros in RESERVED_TYPES else ros


def field_name(ros):
    return ros + "_" if ros in RESERVED_WORDS else ros


# ---------------------------------------------------------------------
# The values.  A node is a tuple:
#   ("int", ros_type, value) ("bool", value) ("f32", value) ("f64", value)
#   ("str", cap, text) ("arr", [node]) ("seq", [node])
#   ("msg", pkg, struct, [(field, node)])

class Gen:
    def __init__(self, key, string_cap, seq_cap, prim_len, msg_len, full=False, long_text=True):
        self.full = full
        self.long_text = long_text
        self.state = zlib.crc32(key.encode()) & 0xFFFFFFFF
        self.n = 0
        self.string_cap = string_cap
        self.seq_cap = seq_cap
        self.prim_len = prim_len
        self.msg_len = msg_len

    def next(self):
        """The next 32-bit value of a fixed generator."""
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF
        self.n += 1
        return self.state

    def integer(self, t):
        lo, hi = INT_RANGE[t]
        h = self.next()
        flavour = self.n % 4
        if flavour == 0:                         # small, either sign where the type has one
            v = 1 + h % 100
            if lo < 0 and (h >> 8) % 2:
                v = -v
        elif flavour == 1:                       # anywhere in the range
            wide = (h << 32) | self.next()
            v = lo + wide % (hi - lo + 1)
        elif flavour == 2:                       # the top of the range
            v = hi - (h % 3)
        else:                                    # a value that sets the high byte
            v = lo + ((h << 8) | (h >> 24)) % (hi - lo + 1)
        if v == 0:
            v = 1
        return v

    def f32(self):
        h = self.next()
        v = (h % 400001 - 200000) / 64.0
        if v == 0 or v == int(v):
            v += 1.0 / 64
        return v

    def f64(self):
        h = self.next()
        v = ((h % 2000003) - 1000001) / 997.0
        if v == 0:
            v = 1.0 / 997
        return v

    def text(self, cap):
        h = self.next()
        word = WORDS[h % len(WORDS)]
        s = "%s_%d/%s" % (word, self.n, WORDS[(h >> 8) % len(WORDS)])
        if self.full and self.long_text:
            # As long as the field holds: the longest string the generated module accepts.
            while len(s) < cap:
                s += "." + WORDS[(h >> 4) % len(WORDS)]
            return s[:cap]
        return s[:min(cap, 12 + (h >> 16) % 8)]


def build_node(gen, t, in_list=False):
    """The node for a value of IDL type `t`."""
    if isinstance(t, D.Array):
        return ("arr", [build_node(gen, t.value_type, True) for _ in range(t.size)])
    if isinstance(t, (D.BoundedSequence, D.UnboundedSequence)):
        cap = min(gen.seq_cap, getattr(t, "maximum_size", gen.seq_cap))
        want = gen.msg_len if isinstance(t.value_type, D.NamespacedType) else gen.prim_len
        count = cap if want is None else min(cap, want)
        return ("seq", [build_node(gen, t.value_type, True) for _ in range(count)], cap)
    if isinstance(t, D.BoundedString):
        return ("str", t.maximum_size, gen.text(t.maximum_size))
    if isinstance(t, D.UnboundedString):
        return ("str", gen.string_cap, gen.text(gen.string_cap))
    if isinstance(t, D.NamespacedType):
        cls = message_class(t.namespaces[0], t.name)
        return build_message(gen, cls, t.namespaces[0], struct_name(t.name))
    if isinstance(t, D.BasicType):
        name = t.typename
        if name == "boolean":
            return ("bool", True if not in_list else gen.next() % 3 != 0)
        if name == "float":
            return ("f32", gen.f32())
        if name == "double":
            return ("f64", gen.f64())
        return ("int", name, gen.integer(name))
    raise SystemExit("unhandled IDL type %r" % (t,))


def message_class(pkg, name):
    mod = importlib.import_module(pkg + ".msg")
    return getattr(mod, name)


def build_message(gen, cls, pkg, sname):
    fields = []
    for fname, ftype in zip(cls.get_fields_and_field_types().keys(), cls.SLOT_TYPES):
        fields.append((fname, build_node(gen, ftype)))
    if not fields:
        # rosidl gives a message with no field the one byte `structure_needs_at_least_one_member`.
        # The Python class has no such attribute, so the middleware writes the zero it holds in C.
        fields.append(("structure_needs_at_least_one_member", ("int", "uint8", 0)))
    return ("msg", pkg, sname, fields, cls)


# ---------------------------------------------------------------------
# The Python instance of a node tree, and the tree read back from one.

def to_python(node, t):
    kind = node[0]
    if kind == "bool":
        return node[1]
    if kind == "f32" or kind == "f64":
        return node[1]
    if kind == "str":
        return node[2]
    if kind == "int":
        return bytes([node[2]]) if node[1] == "octet" else node[2]
    if kind in ("arr", "seq"):
        return [to_python(n, t.value_type) for n in node[1]]
    return instance(node, node[4])


def instance(node, cls):
    m = cls()
    for (fname, child), ftype in zip(node[3], cls.SLOT_TYPES):
        setattr(m, fname, to_python(child, ftype))
    return m


def same(node, value, t, path):
    """Whether `value`, read from a Python message, is what `node` holds."""
    kind = node[0]
    if kind == "msg":
        for (fname, child), ftype in zip(node[3], node[4].SLOT_TYPES):
            same(child, getattr(value, fname), ftype, path + "." + fname)
        return
    if kind in ("arr", "seq"):
        got = list(value)
        assert len(got) == len(node[1]), "%s: length %d, wanted %d" % (path, len(got), len(node[1]))
        for i, child in enumerate(node[1]):
            same(child, got[i], t.value_type, "%s[%d]" % (path, i))
        return
    want = node[2] if kind in ("int", "str") else node[1]
    if kind == "int" and node[1] == "octet":
        got = value[0] if isinstance(value, (bytes, bytearray)) else value
    else:
        got = value
    assert got == want, "%s: read back %r, wanted %r" % (path, got, want)



# ---------------------------------------------------------------------
# The layout of a node, for the bytes the serialiser does not write.
#
# Fast CDR leaves the bytes it skips to align a value as the buffer held
# them, and they are not zero: two runs of the same message differ there.
# The walk below finds those bytes from the values alone, so they can be
# written as zero in the TSV.  Fast CDR also pads a payload of fewer than
# four bytes up to four (a std_msgs/Int8 is eight bytes), and those bytes
# are found the same way.

ALIGN = {"bool": 1, "int8": 1, "uint8": 1, "octet": 1, "char": 1, "int16": 2, "uint16": 2,
         "int32": 4, "uint32": 4, "int64": 8, "uint64": 8, "f32": 4, "f64": 8}


def walk(node, pos, pad):
    """The payload offset after `node` written at `pos`; alignment gaps go to `pad`."""
    kind = node[0]

    def align(n, pos):
        gap = (-pos) % n
        pad.extend(range(pos, pos + gap))
        return pos + gap

    if kind == "msg":
        for _, child in node[3]:
            pos = walk(child, pos, pad)
        return pos
    if kind == "str":
        pos = align(4, pos)
        return pos + 4 + len(node[2]) + 1
    if kind in ("arr", "seq"):
        if kind == "seq":
            pos = align(4, pos) + 4
        for child in node[1]:
            pos = walk(child, pos, pad)
        return pos
    key = kind if kind in ("bool", "f32", "f64") else node[1]
    pos = align(ALIGN[key], pos)
    return pos + ALIGN[key]


def normalised(node, raw):
    """`raw` with the bytes the serialiser did not write set to zero, and where its data ends."""
    pad = []
    end = walk(node, 0, pad)
    wanted = 4 + max(end, 4)
    assert len(raw) == 4 + end or len(raw) == wanted, \
        "%d bytes where the fields end at %d" % (len(raw), 4 + end)
    out = bytearray(raw)
    for i in pad:
        out[4 + i] = 0
    for i in range(4 + end, len(raw)):
        out[i] = 0
    return bytes(out), 4 + end

# ---------------------------------------------------------------------
# The text of a node.

def number(v):
    return repr(v)


def signed(node):
    """The value of an integer node as the Int the generated field holds: a uint64 of 2^63 or more is
    the negative number with the same 64 bits."""
    v = node[2]
    if node[1] == "uint64" and v >= 2 ** 63:
        v -= 2 ** 64
    return v


def flatten(node, path, out):
    kind = node[0]
    if kind == "msg":
        for fname, child in node[3]:
            flatten(child, path + "." + fname if path else fname, out)
    elif kind in ("arr", "seq"):
        if kind == "seq":
            out.append("%s#=%d" % (path, len(node[1])))
        for i, child in enumerate(node[1]):
            flatten(child, "%s[%d]" % (path, i), out)
    elif kind == "bool":
        out.append("%s=%s" % (path, "true" if node[1] else "false"))
    elif kind in ("f32", "f64"):
        out.append("%s=%s" % (path, number(node[1])))
    elif kind == "str":
        out.append("%s=%s" % (path, node[2]))
    else:
        out.append("%s=%d" % (path, signed(node)))


# ---------------------------------------------------------------------
# The novo-lang source of a node.

class Src:
    def __init__(self, string_cap, seq_cap, pkg):
        self.string_cap = string_cap
        self.seq_cap = seq_cap
        self.pkg = pkg
        self.pre = []
        self.count = 0

    def fresh(self, stem):
        self.count += 1
        return "%s_%d" % (stem, self.count)

    def num(self, v):
        if v == -(2 ** 63):
            return "(-9223372036854775807 - 1)"
        return repr(v) if isinstance(v, float) else str(v)

    def scalar(self, node):
        kind = node[0]
        if kind == "bool":
            return "true" if node[1] else "false"
        if kind == "f64":
            return self.num(node[1])
        if kind == "f32":
            return self.cast(node[1], "fp32")
        ty = NOVO_INT[node[1]]
        if ty == "Int":
            return self.num(signed(node))
        return self.cast(node[2], ty)

    def cast(self, v, ty):
        """A literal as a narrower type; a negative one is parenthesised, as `novo fmt` leaves it."""
        s = self.num(v)
        return "(%s) as %s" % (s, ty) if s.startswith("-") else "%s as %s" % (s, ty)

    def qual(self, pkg, name):
        return "%s.%s" % (pkg, name)

    def elem_type(self, node):
        kind = node[0]
        if kind == "msg":
            return self.qual(node[1], node[2])
        if kind == "str":
            return "String[%d]" % node[1]
        if kind == "bool":
            return "Bool"
        if kind == "f64":
            return "Float"
        if kind == "f32":
            return "fp32"
        return NOVO_INT[node[1]]

    def expr(self, node, indent):
        """An expression for `node`; lines it needs first go to self.pre."""
        kind = node[0]
        if kind == "msg":
            pad = " " * (indent + 4)
            items = []
            for fname, child in node[3]:
                items.append("%s%s: %s" % (pad, field_name(fname), self.expr(child, indent + 4)))
            return "%s {\n%s }" % (self.qual(node[1], node[2]), ",\n".join(items))
        if kind == "str":
            v = self.fresh("s")
            self.pre.append('        var %s: String[%d] = String.new()' % (v, node[1]))
            self.pre.append('        let _ = %s.push_str("%s")' % (v, node[2]))
            return v
        if kind == "arr":
            parts = [self.expr(c, indent + 4) for c in node[1]]
            return "[" + wrap(parts, indent + 4) + "]"
        if kind == "seq":
            v = self.fresh("v")
            ety = self.elem_type(node[1][0])
            self.pre.append("        var %s: Vec[%s; %d] = Vec.new()" % (v, ety, node[2]))
            for c in node[1]:
                e = self.expr(c, 8)
                self.pre.append("        let _ = %s.push(%s)" % (v, e))
            return v
        return self.scalar(node)


def checks(node, access, out):
    """The assertion lines that compare a decoded message with `node`."""
    kind = node[0]
    if kind == "msg":
        for fname, child in node[3]:
            checks(child, "%s.%s" % (access, field_name(fname)), out)
    elif kind == "arr":
        for i, child in enumerate(node[1]):
            checks(child, "%s[%d]" % (access, i), out)
    elif kind == "seq":
        out.append("    test.assert_eq(%s.len(), %d)" % (access, len(node[1])))
        for i, child in enumerate(node[1]):
            checks(child, "%s[%d]" % (access, i), out)
    elif kind == "bool":
        out.append("    test.assert_eq(%s, %s)" % (access, "true" if node[1] else "false"))
    elif kind == "f64":
        out.append("    test.assert(%s == %s)" % (access, Src(0, 0, "").num(node[1])))
    elif kind == "f32":
        out.append("    test.assert((%s as Float) == %s)" % (access, Src(0, 0, "").num(node[1])))
    elif kind == "str":
        out.append('    test.assert(%s.eq_str("%s"))' % (access, node[2]))
    else:
        ty = NOVO_INT[node[1]]
        lhs = access if ty == "Int" else "%s as Int" % access
        out.append("    test.assert_eq(%s, %s)" % (lhs, Src(0, 0, "").num(signed(node))))


def wrap(parts, indent):
    """Elements joined with commas, wrapped to 100 columns."""
    out = ""
    col = indent
    first = True
    for p in parts:
        if "\n" in p:
            out += ("" if first else ",\n" + " " * indent) + p
            col = indent
        elif first:
            out += p
            col += len(p) + 2
        elif col + len(p) + 2 > 100:
            out += ",\n" + " " * indent + p
            col = indent + len(p) + 2
        else:
            out += ", " + p
            col += len(p) + 2
        first = False
    return out


# ---------------------------------------------------------------------
# The set of types.

def bundled(pkg):
    """(kind, ros name) for each message and service half in src/interfaces/<pkg>."""
    base = os.path.join(PKG, "src", "interfaces", pkg)
    out = []
    for kind in ("msg", "srv"):
        d = os.path.join(base, kind)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith("." + kind):
                    out.append((kind, f[:-len(kind) - 1]))
    return out


def one_type(pkg, kind, name):
    """The rows of one definition: a message is one, a service two."""
    rows = []
    if kind == "msg":
        halves = [("msg", name, message_class(pkg, name))]
    else:
        mod = importlib.import_module(pkg + ".srv")
        srv = getattr(mod, name)
        halves = [("srv", name + "_Request", srv.Request), ("srv", name + "_Response", srv.Response)]
    scap, qcap = CAPS.get(pkg, DEFAULT_CAPS)
    for k, ros, cls in halves:
        full = "%s/%s/%s" % (pkg, k, ros)
        sname = struct_name(ros) if k == "msg" else ros.replace("_Request", "Request").replace("_Response", "Response")
        base_values = None
        # The first instance has short strings and sequences of two or three; the second, where
        # it differs and fits, has every string and every sequence as long as the field holds.
        for variant in ("", "#full"):
            # Full: every string and sequence at its capacity; failing that, the sequences of
            # messages cut to one element; failing that, the strings short as well.
            tries = (((3, 2, True), (2, 1, True), (1, 1, True)) if variant == ""
                     else ((None, None, True), (None, 1, True), (None, 1, False)))
            for prim_len, msg_len, long_text in tries:
                gen = Gen(full + variant, scap, qcap, prim_len, msg_len, full=variant != "",
                          long_text=long_text)
                node = build_message(gen, cls, pkg, sname)
                data = ser.serialize_message(instance(node, cls))
                if len(data) <= CDR_CAP:
                    break
            else:
                if variant == "":
                    print("skipped %s: %d bytes" % (full, len(data)), file=sys.stderr)
                    break
                print("no full-length vector for %s: %d bytes" % (full, len(data)), file=sys.stderr)
                continue
            if variant == "":
                base_values = tsv_values(node)
            elif not has_dynamic(node) or tsv_values(node) == base_values:
                continue
            data, end = normalised(node, data)
            # The zeroed bytes and the shorter form, with nothing after the last field,
            # read back to the same values through the middleware.
            for form in (data, data[:end]):
                check_read_back(node, ser.deserialize_message(form, cls), cls, full)
            rows.append((full + variant, sname, k, node, data, scap, qcap))
    return rows


def has_dynamic(node):
    """Whether `node` holds a string or a sequence."""
    if node[0] in ("str", "seq"):
        return True
    if node[0] == "msg":
        return any(has_dynamic(c) for _, c in node[3])
    if node[0] == "arr":
        return any(has_dynamic(c) for c in node[1])
    return False


def check_read_back(node, back, cls, path):
    for (fname, child), ftype in zip(node[3], cls.SLOT_TYPES):
        same(child, getattr(back, fname), ftype, path + "." + fname)


# ---------------------------------------------------------------------
# The files.

HEADER_TSV = """# Test vectors from the ROS 2 middleware, written by scripts/rclpy_vectors.py on {date}.
# One row per message and per service half of src/interfaces/ (not cdr_test_msgs, which is no ROS package),
# and where the type has a string or a sequence a second row, named with #full after the type, in which each
# string and each sequence is as long as the generated module's field holds, where that fits in the 1,024 bytes of a message.
# Each row is one instance with every field set to a value other than its default, serialised by
# rclpy.serialization.serialize_message ({rclpy}) through {rmw}, with Fast CDR {fastcdr};
# the definitions are those of ROS 2 Jazzy, std_msgs {stdmsgs}.
# Columns, separated by a tab: the full type name; the byte order of the bytes (le or be);
# the values, as path=value separated by a space, where path# is the length of a sequence;
# the bytes as lowercase hex, the four-byte encapsulation header first.
# The bytes Fast CDR skips to align a value hold whatever its buffer held (the same message gives 84 in one run
# and 9c in the next), so they are written here as 00, found by walking the values; the middleware reads the
# message back to the same values with them zeroed.  It also writes a payload of fewer than four bytes as four
# (std_msgs/Int8 is 0001000005000000); the extra bytes are written as 00 and the message reads back without them.
# A float32 is a multiple of 1/64 below 2^18 and is exact; a uint64 is printed as the Int that holds the same 64 bits.
"""


def pkg_version(name):
    try:
        out = subprocess.run(["dpkg-query", "-W", "-f=${Version}", name],
                             capture_output=True, text=True, check=True).stdout
        return "%s %s" % (name, out.split("-")[0])
    except Exception:
        return name


def tsv_values(node):
    out = []
    flatten(node, "", out)
    return " ".join(out)


def test_file(pkg, rows):
    scap, qcap = CAPS.get(pkg, DEFAULT_CAPS)
    L = []
    a = L.append
    a("// jazzy_vectors_%s_tests.nv -- the messages of %s as the ROS 2 middleware serialises them." % (pkg, pkg))
    a("//")
    a("// Do not edit this file.  scripts/rclpy_vectors.py writes it, with tests/jazzy_vectors.tsv.")
    a("//")
    a("// Each test builds one message from literal values, encodes it and compares the bytes with")
    a("// the row of tests/jazzy_vectors.tsv that `rclpy.serialization.serialize_message` produced")
    a("// from the same values; decodes the middleware's bytes and checks every field; encodes the")
    a("// result again; and sends it through the other byte order and back.  The bytes Fast CDR")
    a("// skips to align a value are zero in the vector, because the middleware leaves them as its")
    a("// buffer held them; see the header of the TSV.")
    a("")
    a("use std.bytes")
    a("use std.fs")
    a("use std.str")
    a("use std.test")
    a("use cdr")
    a("use cdrbytes")
    pkgs = {pkg}
    for r in rows:
        collect_pkgs(r[3], pkgs)
    for p in sorted(pkgs):
        a("use %s" % p)
    a("")
    a("// The hex of the row for `name`.")
    a("fn vector(name: Str) -> Str [fs]")
    a('    let text = fs.read("tests/jazzy_vectors.tsv") ?? ""')
    a('    for line in str.split(text, "\\n")')
    a('        if not str.starts_with(line, "#")')
    a('            let cols = str.split(line, "\\t")')
    a("            if list.len(cols) == 4 and cols[0] == name")
    a("                return cols[3]")
    a('    test.fail("no vector for ${name}")')
    a('    ""')
    a("")
    a("// A writer in the byte order the vector's header names.")
    a("fn writer_like(hex: Str) -> cdr.Writer")
    a('    if str.starts_with(hex, "0000")')
    a("        cdr.writer_be()")
    a("    else")
    a("        cdr.writer_le()")
    a("")
    a("// A writer in the other byte order.")
    a("fn writer_unlike(hex: Str) -> cdr.Writer")
    a('    if str.starts_with(hex, "0000")')
    a("        cdr.writer_le()")
    a("    else")
    a("        cdr.writer_be()")
    a("")
    a("// The writer's bytes are the vector, or the vector without the zero bytes the middleware adds to")
    a("// bring a payload of fewer than four bytes up to four.")
    a("fn expect_bytes(got: Str, want: Str)")
    a("    test.assert(str.len(got) <= str.len(want))")
    a("    test.assert_eq_str(str.slice(want, 0, str.len(got)), got)")
    a("    let rest = str.slice(want, str.len(got), str.len(want))")
    a('    test.assert_eq_str(rest, str.repeat("0", str.len(rest)))')
    a("    if str.len(rest) > 0")
    a("        test.assert_eq(str.len(want), 16)")
    a("")
    a("fn hex_of(w: cdr.Writer) -> Str")
    a("    bytes.to_hex(cdrbytes.to_bytes(w))")
    a("")
    a("fn reader_of_hex(h: Str) -> cdr.Reader")
    a("    cdrbytes.reader_from_bytes(bytes.from_hex(h) ?? bytes.zeros(0))")
    a("")
    for full, sname, kind, node, data, _, _ in rows:
        a("// %s" % full)
        a("@test")
        a("fn test_vector_%s_%s() [io, fs]" % (pkg, full.split("/", 2)[2].replace("#", "_")))
        src = Src(scap, qcap, pkg)
        e = src.expr(node, 4)
        a('    let want = vector("%s")' % full)
        for line in src.pre:
            a(line[4:])
        a("    let m = %s" % e)
        ty = "%s.%s" % (pkg, sname)
        a("    // The message built from the values encodes to the middleware's bytes.")
        a("    var w = writer_like(want)")
        a('    test.assert_eq_str(cdr.status_name(m.encode(var w)), "success")')
        a("    expect_bytes(hex_of(w), want)")
        a("    // The middleware's bytes decode to those values.")
        a("    var r = reader_of_hex(want)")
        a("    var back = %s.new()" % ty)
        a('    test.assert_eq_str(cdr.status_name(back.decode_into(var r)), "success")')
        a("    test.assert_eq(r.remaining(), (str.len(want) - str.len(hex_of(w))) / 2)")
        cl = []
        checks(node, "back", cl)
        L.extend(cl)
        a("    // They encode to the same bytes again.")
        a("    var w2 = writer_like(want)")
        a('    test.assert_eq_str(cdr.status_name(back.encode(var w2)), "success")')
        a("    test.assert_eq_str(hex_of(w2), hex_of(w))")
        a("    // The other byte order decodes to the same message, which encodes to the first bytes.")
        a("    var wo = writer_unlike(want)")
        a('    test.assert_eq_str(cdr.status_name(m.encode(var wo)), "success")')
        a("    var ro = cdrbytes.reader_from_bytes(cdrbytes.to_bytes(wo))")
        a("    var other = %s.new()" % ty)
        a('    test.assert_eq_str(cdr.status_name(other.decode_into(var ro)), "success")')
        a("    var w3 = writer_like(want)")
        a('    test.assert_eq_str(cdr.status_name(other.encode(var w3)), "success")')
        a("    test.assert_eq_str(hex_of(w3), hex_of(w))")
        a("")
    return "\n".join(L)


def collect_pkgs(node, out):
    if node[0] == "msg":
        out.add(node[1])
        for _, c in node[3]:
            collect_pkgs(c, out)
    elif node[0] in ("arr", "seq"):
        for c in node[1]:
            collect_pkgs(c, out)


def main():
    tsv = []
    for pkg in PACKAGES:
        rows = []
        for kind, name in bundled(pkg):
            rows.extend(one_type(pkg, kind, name))
        for full, sname, kind, node, data, _, _ in rows:
            tsv.append("%s\tle\t%s\t%s" % (full, tsv_values(node), data.hex()))
        text = test_file(pkg, rows)
        path = os.path.join(PKG, "tests", "jazzy_vectors_%s_tests.nv" % pkg)
        with open(path, "w") as f:
            f.write(text)
        # Canonical style, which also drops a package prefix from a type where the type is
        # in scope without it.
        novo = os.environ.get("NOVO", os.path.expanduser("~/.novo/bin/novo"))
        subprocess.run([novo, "fmt", path], check=True, capture_output=True)
        print("%s: %d types" % (pkg, len(rows)), file=sys.stderr)
    head = HEADER_TSV.format(
        date=datetime.date.today().isoformat(),
        rclpy=pkg_version("ros-jazzy-rclpy"),
        rmw=pkg_version("ros-jazzy-rmw-fastrtps-cpp"),
        fastcdr=pkg_version("ros-jazzy-fastcdr"),
        stdmsgs=pkg_version("ros-jazzy-std-msgs"))
    with open(os.path.join(PKG, "tests", "jazzy_vectors.tsv"), "w") as f:
        f.write(head + "\n".join(tsv) + "\n")
    print("%d vectors" % len(tsv), file=sys.stderr)


if __name__ == "__main__":
    main()
