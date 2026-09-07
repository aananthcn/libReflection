#!/usr/bin/env python3
"""Generates reflection registration for arbitrary C++ types --
including ones with private members, constructors, or methods -- by
reading DWARF debug info from a compiled object file.

Unlike tools/generate_reflection_names.py (built, verified, and
reverted -- see docs/adr/0012), this does NOT parse C++ source text to
understand a class's members at all. It reads compiler-emitted DWARF,
which records every data member's name, type, and byte offset
regardless of its C++ access level (a debugger can already inspect a
private field; the data is there unconditionally). See
docs/adr/0013-dwarf-based-reflection-generation.md.

The generated registration never writes an access-checked C++
expression (no `decltype(Type::member)`, no `offsetof(Type, member)`)
-- every value (name, type name, offset, size) is embedded as a
literal, straight from DWARF, so it can never fail to compile due to
access control, and a member that doesn't confidently resolve is
simply omitted (an incomplete-but-correct reflection), never guessed.

The only text-scanning this script does is finding top-level
`struct NAME`/`class NAME` declarations, to know which type NAMES to
look for in the DWARF -- it never needs to understand a class BODY
(no need to distinguish public/private, spot bit-fields, etc.); DWARF
already carries all of that.

Two modes, both driven by CMake (see cmake/GenerateDwarfReflection.cmake):

  --emit-driver <source.cpp> <output_driver.cpp>
      Discovers every struct/class in <source.cpp> and writes a
      throwaway "driver" .cpp that #includes <source.cpp> and declares
      one instance of each discovered type. An actual instance is
      required to force the compiler to emit that type's FULL DWARF
      info -- a type merely named in an unevaluated context like
      sizeof() is not guaranteed to get full debug output (verified
      empirically). The driver is compiled with -g and never linked
      anywhere, so #include-ing an arbitrary .cpp (even one with its
      own main()) is safe: it's never combined with another
      translation unit.

  --extract <object.o> <source.cpp> <output_header.hpp> [--objdump <path>]
      Re-discovers the same type names from <source.cpp>, reads DWARF
      from the compiled <object.o> (normally the driver's object file
      from --emit-driver), and writes <output_header.hpp> with a
      REFLECT_DWARF_CLASS_BEGIN/REFLECT_DWARF_MEMBER/
      REFLECT_DWARF_CLASS_END block (see src/ReflectionMacros.hpp) per
      type it could find in the debug info. --objdump defaults to the
      plain host "objdump"; a cross-build MUST pass the toolchain's
      own (e.g. CMake's ${CMAKE_OBJDUMP}, or QNX SDP's target-specific
      "<triple>-objdump") -- verified against QNX SDP 8.0's own
      objdump for an x86_64 target object (see docs/adr/0013's "Tested
      against the real QNX SDP 8.0 toolchain").
"""

import re
import subprocess
import sys
from pathlib import Path

TYPE_DECL_RE = re.compile(r"\b(?:struct|class)\s+([A-Za-z_]\w*)\s*[:{]")

DIE_RE = re.compile(
    r"^\s*<(\d+)><([0-9a-fA-F]+)>:\s*Abbrev Number:\s*\d+(?:\s*\(([^)]+)\))?"
)
ATTR_RE = re.compile(r"^\s*<[0-9a-fA-F]+>\s*(DW_AT_\w+)\s*:\s*(.*)$")
REF_RE = re.compile(r"<(?:0x)?([0-9a-fA-F]+)>")

TYPE_DIE_TAGS = ("DW_TAG_structure_type", "DW_TAG_class_type")

# Comments AND string/char literals must be stripped before scanning
# for type declarations -- text that merely *looks* like "class Name{"
# inside a string literal (e.g. a log message) or a comment is a real,
# observed false positive otherwise.
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_CHAR_LITERAL_RE = re.compile(r"'(?:\\.|[^'\\])*'")


def _strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    text = _LINE_COMMENT_RE.sub(" ", text)
    return text


def _strip_noise(text: str) -> str:
    text = _strip_comments(text)
    text = _STRING_LITERAL_RE.sub('""', text)
    text = _CHAR_LITERAL_RE.sub("' '", text)
    return text


LOCAL_INCLUDE_RE = re.compile(r'#\s*include\s*"([^"]+)"')
# A template can't be safely touch-instantiated (no template arguments
# are known), so a "struct/class Name" immediately preceded by a
# template<...> parameter list must be excluded at discovery time --
# generating "Name touch_Name;" for a bare template name is a compile
# error (verified), not a gracefully-skipped case.
_TEMPLATE_PRECEDING_RE = re.compile(r"template\s*<[^;{}]*>\s*$")


def discover_type_names(source_path: str, _visited=None):
    """Scans source_path, and every LOCAL ("...") header it #includes
    (transitively), for top-level struct/class declarations. System/
    library (<...>) includes are never followed. A type declared
    anywhere in this file set -- main.cpp itself, or a header it pulls
    in -- is discovered without needing to be listed anywhere."""
    if _visited is None:
        _visited = set()
    path = Path(source_path).resolve()
    if path in _visited or not path.is_file():
        return []
    _visited.add(path)

    raw = path.read_text()
    # Includes are found in the comments-only-stripped text -- an
    # #include's quoted path is a real path, not a string literal to
    # blank out (blanking it out was a real bug caught by testing:
    # #include "HelloWorld.hpp" became #include "" and the header was
    # silently never followed).
    comments_stripped = _strip_comments(raw)
    text = _STRING_LITERAL_RE.sub('""', comments_stripped)
    text = _CHAR_LITERAL_RE.sub("' '", text)

    names = []
    seen = set()
    for m in TYPE_DECL_RE.finditer(text):
        if _TEMPLATE_PRECEDING_RE.search(text[:m.start()]):
            continue
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)

    for m in LOCAL_INCLUDE_RE.finditer(comments_stripped):
        included = (path.parent / m.group(1)).resolve()
        for name in discover_type_names(str(included), _visited):
            if name not in seen:
                seen.add(name)
                names.append(name)

    return names


def emit_driver(source_path: str, output_path: Path):
    source_abs = str(Path(source_path).resolve())
    type_names = discover_type_names(source_path)
    lines = [f'#include "{source_abs}"', ""]
    if type_names:
        lines.append("namespace reflect_dwarf_extraction_touch {")
        for name in type_names:
            # A plain "Type touch_Type;" only works for default-
            # constructible types -- verified this fails to compile
            # for e.g. a class whose only constructor takes arguments,
            # which is common for encapsulated types (exactly the
            # case this tool exists for). Wrapping it in a union with
            # an explicit no-op default constructor/destructor forces
            # the SAME full debug-info emission (an instance of the
            # union has a real Encapsulated sub-object, verified via
            # DWARF) without ever constructing/destructing the member
            # itself, so no constructor arguments are ever needed.
            lines.append(f"union Touch_{name} {{")
            lines.append(f"    {name} value;")
            lines.append("    char dummy;")
            lines.append(f"    Touch_{name}() : dummy(0) {{}}")
            lines.append(f"    ~Touch_{name}() {{}}")
            lines.append("};")
            lines.append(f"Touch_{name} touch_{name};")
        lines.append("}")
    output_path.write_text("\n".join(lines) + "\n")


def dump_dwarf(object_path: str, objdump: str = "objdump") -> str:
    """objdump defaults to the plain host binary, but a cross-build
    MUST pass the toolchain's own objdump (e.g. CMake's
    ${CMAKE_OBJDUMP}) explicitly -- verified against a real QNX SDP
    8.0 x86_64 target object that the host's objdump happens to read
    QNX-compiled objects correctly too (only trivial 0/0x0 value-
    formatting differences, nothing in a field this tool reads), but
    that's not a guarantee to rely on for every toolchain/architecture,
    so the caller should still pass the matching tool when known."""
    result = subprocess.run(
        [objdump, "--dwarf=info", object_path],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def parse_name(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("(") and ":" in raw:
        return raw.rsplit(":", 1)[-1].strip()
    return raw


def parse_ref(raw: str):
    m = REF_RE.search(raw)
    return int(m.group(1), 16) if m else None


def parse_dies(dwarf_text: str):
    dies = []
    current = None
    for line in dwarf_text.split("\n"):
        m = DIE_RE.match(line)
        if m:
            if current is not None:
                dies.append(current)
            current = {
                "depth": int(m.group(1)),
                "offset": int(m.group(2), 16),
                "tag": m.group(3),
                "attrs": {},
            }
            continue
        m2 = ATTR_RE.match(line)
        if m2 and current is not None:
            current["attrs"][m2.group(1)] = m2.group(2).strip()
    if current is not None:
        dies.append(current)
    return dies


def resolve_type(offset, by_offset, _seen=None):
    """Returns (type_name, byte_size) for a DW_AT_type reference,
    unwrapping const/volatile/typedef qualifiers. Pointers are named
    "<inner>*" without recursing into the pointee's members (matches
    docs/adr/0004's opaque-leaf policy for pointers). Anything
    unresolvable becomes ("<unknown>", 0) rather than a guess."""
    if _seen is None:
        _seen = set()
    if offset is None or offset in _seen:
        return ("<unknown>", 0)
    _seen.add(offset)
    die = by_offset.get(offset)
    if die is None:
        return ("<unknown>", 0)
    tag = die["tag"]
    attrs = die["attrs"]
    if tag == "DW_TAG_base_type" or tag in TYPE_DIE_TAGS:
        name = parse_name(attrs.get("DW_AT_name", "<unknown>"))
        size = int(attrs.get("DW_AT_byte_size", "0") or 0)
        return (name, size)
    if tag == "DW_TAG_pointer_type":
        inner_name, _ = resolve_type(parse_ref(attrs.get("DW_AT_type", "")), by_offset, _seen)
        return (f"{inner_name}*", 8)
    if tag in ("DW_TAG_const_type", "DW_TAG_volatile_type", "DW_TAG_typedef"):
        inner_ref = parse_ref(attrs.get("DW_AT_type", ""))
        if inner_ref is None:
            return ("void", 0)
        return resolve_type(inner_ref, by_offset, _seen)
    name = parse_name(attrs.get("DW_AT_name", "<unknown>"))
    size = int(attrs.get("DW_AT_byte_size", "0") or 0)
    return (name, size)


def find_type(type_name: str, dies, by_offset):
    """Returns (byte_size, [(member_name, member_type, offset, size), ...])
    for the first structure/class DIE named type_name, or None if not
    found. Only DIRECT DW_TAG_member children are collected -- methods,
    constructors, and nested types (any other tag) are skipped, and
    grandchildren (e.g. a constructor's formal parameters) are walked
    past via depth tracking without being mistaken for members."""
    for i, die in enumerate(dies):
        if die["tag"] not in TYPE_DIE_TAGS:
            continue
        name_attr = die["attrs"].get("DW_AT_name")
        if name_attr is None or parse_name(name_attr) != type_name:
            continue
        depth = die["depth"]
        byte_size = int(die["attrs"].get("DW_AT_byte_size", "0") or 0)
        members = []
        j = i + 1
        while j < len(dies) and dies[j]["depth"] > depth:
            child = dies[j]
            if child["depth"] == depth + 1 and child["tag"] == "DW_TAG_member":
                mname = parse_name(child["attrs"].get("DW_AT_name", ""))
                moffset = int(child["attrs"].get("DW_AT_data_member_location", "0") or 0)
                type_ref = parse_ref(child["attrs"].get("DW_AT_type", ""))
                mtype, msize = resolve_type(type_ref, by_offset)
                if mname:
                    members.append((mname, mtype, moffset, msize))
            j += 1
        return byte_size, members
    return None


def extract(object_path: str, source_path: str, output_path: Path, objdump: str = "objdump"):
    type_names = discover_type_names(source_path)
    dwarf_text = dump_dwarf(object_path, objdump)
    dies = parse_dies(dwarf_text)
    by_offset = {d["offset"]: d for d in dies}

    lines = [
        "// AUTO-GENERATED by tools/generate_dwarf_reflection.py -- do not edit by hand.",
        "// Regenerate by re-running the build (this runs automatically).",
        "// See docs/adr/0013-dwarf-based-reflection-generation.md.",
        "//",
        "// This MUST be a header, #include'd by every translation unit that",
        "// calls reflect::Reflect<T>() for one of the types below -- explicit",
        "// template specializations must be visible in the TU that",
        "// instantiates them (see docs/adr/0010's declare-before-use rule).",
        "#pragma once",
        "",
        '#include "Reflection.hpp"',
        "",
    ]

    for type_name in type_names:
        result = find_type(type_name, dies, by_offset)
        if result is None:
            lines.append(f"// {type_name}: not found in DWARF info -- skipped, not guessed.")
            continue
        byte_size, members = result
        lines.append(f"REFLECT_DWARF_CLASS_BEGIN({type_name}, {byte_size})")
        for mname, mtype, moffset, msize in members:
            lines.append(
                f'    REFLECT_DWARF_MEMBER("{mname}", "{mtype}", {moffset}, {msize})'
            )
        lines.append("REFLECT_DWARF_CLASS_END()")
        lines.append("")

    output_path.write_text("\n".join(lines) + "\n")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--emit-driver"] and len(args) == 3:
        emit_driver(args[1], Path(args[2]))
        return
    if args[:1] == ["--extract"] and len(args) in (4, 6):
        objdump = "objdump"
        if len(args) == 6:
            if args[4] != "--objdump":
                print(__doc__, file=sys.stderr)
                sys.exit(1)
            objdump = args[5]
        extract(args[1], args[2], Path(args[3]), objdump)
        return
    print(__doc__, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
