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
`struct NAME`/`class NAME` declarations (plus, for a template, actual
USES of it elsewhere in the same file set, e.g. "Box<int> value;" --
a template's bare declaration alone can't be touch-instantiated), to
know which type NAMES to look for in the DWARF -- it never needs to
understand a class BODY (no need to distinguish public/private, spot
bit-fields, etc.); DWARF already carries all of that.

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

# A scoped enum ("enum class" / "enum struct") also carries the
# "class"/"struct" keyword, but it is not a reflectable class -- if it
# were discovered here, DWARF extraction would later find an
# enumeration DIE instead of a structure/class one and emit a spurious
# "entire type skipped" #warning for a type that was never meant to be
# reflected. The optional "enum" prefix is captured so the scan can
# skip those matches.
TYPE_DECL_RE = re.compile(
    r"\b(?P<enum>enum\s+)?(?:struct|class)\s+(?P<name>[A-Za-z_]\w*)\s*[:{]"
)

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
# A template class declaration itself can't be safely touch-
# instantiated (no template arguments are known from the declaration
# alone) -- a "struct/class Name" immediately preceded by a
# template<...> parameter list is excluded from the plain type-name
# list. Its base NAME is tracked separately (see
# discover_type_names()), AND its parameter-list text is captured
# (group 1) so _classify_template_params() can later tell a type
# parameter ("typename T") from a non-type one ("int N") -- this is
# what lets a USE's arguments be checked against the right EXPECTED
# kind per position, not just checked in isolation for "looks like a
# plausible type or literal" (see _TEMPLATE_ARG_SHAPE_RE) -- so actual
# USES of it elsewhere in the source -- e.g. "Box<int> value;" -- can
# be found and touched instead; generating "Name touch_Name;" for a
# bare template name (no arguments) is a compile error (verified), not
# a gracefully-skipped case.
_TEMPLATE_HEADER_RE = re.compile(r"template\s*<([^;{}]*)>\s*$")

# Matches just a known template name immediately followed by "<" -- the
# OPENING of its argument list. The argument list itself (which may
# contain further nested "<...>", e.g. "Box<int>" inside
# "Pair<int, Box<int>>") is then extracted separately by
# _find_balanced_template_args(), which counts bracket depth -- no
# regex can match arbitrarily-nested brackets on its own.
def _template_use_re(name: str) -> "re.Pattern":
    return re.compile(r"\b" + re.escape(name) + r"\s*<")


def _find_balanced_template_args(text: str, open_index: int):
    """text[open_index] must be the "<" that opens a template-use
    argument list. Scans forward counting bracket depth (each "<" +1,
    each ">" -1) to find the MATCHING ">" -- the one that brings depth
    back to 0 -- so a nested argument list's own "<"/">" (e.g. the
    inner "Box<int>" in "Pair<int, Box<int>>") doesn't end the scan
    early. Returns (raw_args_text, end_index) where raw_args_text is
    everything strictly between the opening "<" and its match, and
    end_index is the index just past that match -- or None if depth
    never returns to 0 before the text ends, or a character this
    scanner never trusts inside a template argument list (";", "{",
    "}", "(" -- an expression or statement shape, not a type/literal
    list) appears at any depth. This is a bracket counter, not a real
    C++ tokenizer: ">>" in the SOURCE TEXT for closing two levels (as
    someone actually writes "Box<Box<int>>") is just two adjacent ">"
    characters here, each closing one level -- no special-casing
    needed, unlike an actual C++ parser's ">>"-as-one-token ambiguity."""
    depth = 1
    i = open_index + 1
    n = len(text)
    while i < n:
        c = text[i]
        if c in ";{}(":
            return None
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i], i + 1
        i += 1
    return None


# A LEAF template argument (one with no further nested "<...>" of its
# own) is only trusted if it looks like a plain type name (optionally
# qualified, pointer/reference-decorated) or an integer literal (for a
# non-type template parameter) -- never an arbitrary expression. This
# exists specifically to reject a false-positive match like
# "Box < 5 > threshold" (a chained relational comparison, not a
# template instantiation): most such expressions won't have this
# shape, and any that do are the one documented residual risk of this
# heuristic -- see docs/adr/0013.
_TEMPLATE_ARG_SHAPE_RE = re.compile(r"^[\w:\s*&-]+$")

# Matches a nested argument's HEAD: a (possibly namespace-qualified)
# name immediately followed by "<" -- e.g. "Box" in "Box<int>", or
# "std::vector" in "std::vector<int>". Used by _normalize_arg() to
# decide whether an argument is itself a nested template instantiation
# (recurse via _find_balanced_template_args()) or a leaf value (match
# against _TEMPLATE_ARG_SHAPE_RE instead).
_NESTED_ARG_HEAD_RE = re.compile(r"^([\w:]+)\s*<")

# An argument accepted by _TEMPLATE_ARG_SHAPE_RE is either a NON-TYPE
# value (an integer or boolean literal -- the only such shapes this
# scanner accepts) or a TYPE name; _arg_kind() tells the two apart so
# they can be checked against the declared template PARAMETER's own
# kind (see _classify_template_params()) -- this is the actual fix for
# "Box < 5 > threshold" being indistinguishable from `Box<5>` by shape
# alone (see docs/adr/0013): "5" only READS as a plausible non-type
# argument for a template that actually DECLARES a non-type parameter
# there. For `template <typename T> struct Box`, "5" can never be a
# valid argument regardless of any comparison/declaration ambiguity --
# no C++ overload resolution or shadowing changes that -- so it's
# always correct to reject it outright, never a guess.
_INTEGER_LITERAL_RE = re.compile(r"^[+-]?(?:0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)$")
_BOOL_LITERAL_RE = re.compile(r"^(?:true|false)$")


def _arg_kind(normalized_arg: str) -> str:
    """Classifies one already-normalized, already-shape-validated
    template argument as "nontype" (an integer or boolean literal) or
    "type" (everything else _TEMPLATE_ARG_SHAPE_RE/_NESTED_ARG_HEAD_RE
    accept: a plain or qualified type name, pointer/reference-decorated
    or not, or a nested template instantiation)."""
    if _INTEGER_LITERAL_RE.match(normalized_arg) or _BOOL_LITERAL_RE.match(normalized_arg):
        return "nontype"
    return "type"


# Keywords that start a NON-TYPE template parameter's declared type
# (e.g. "int N", "unsigned long Flags", "bool Enabled", "auto V" for a
# C++17 placeholder non-type parameter) -- deliberately NOT exhaustive:
# anything not on this list, and not starting with "typename"/"class"
# either, makes _classify_template_params() give up on the WHOLE
# template (fall back to the old kind-agnostic shape check for it, see
# _normalize_arg_list) rather than guess a parameter's kind wrong.
_NONTYPE_PARAM_KEYWORDS = (
    "bool", "char", "char8_t", "char16_t", "char32_t", "wchar_t",
    "short", "int", "long", "signed", "unsigned", "float", "double",
    "size_t", "std::size_t", "ptrdiff_t", "std::ptrdiff_t", "auto",
)
_NONTYPE_PARAM_KEYWORD_RE = re.compile(
    r"^(?:" + "|".join(re.escape(k) for k in _NONTYPE_PARAM_KEYWORDS) + r")\b"
)


def _classify_template_params(params_text: str):
    """Parses a template's declared parameter-list text (e.g.
    "typename T" or "typename T, int N" -- the group 1 captured by
    _TEMPLATE_HEADER_RE) into an ordered list of (kind, is_pack) pairs,
    kind being "type" (a `typename`/`class` parameter) or "nontype" (a
    parameter declared with one of _NONTYPE_PARAM_KEYWORDS). Returns
    None if ANY parameter's kind can't be confidently determined (a
    template-template parameter, e.g. "template <typename> class C";
    an unrecognized non-type parameter type; or simply unparseable) --
    callers must then skip kind-matching for this template entirely
    (fall back to the previous, kind-agnostic behavior), never reject
    (or accept) more than the old behavior did out of a bad guess at
    the template's own signature.

    A default value ("typename U = T") only affects whether that
    parameter is OPTIONAL in a real instantiation, not its kind --
    stripped before classifying. A pack ("typename... Ts", "int... Ns")
    is marked is_pack=True, so _param_kind_at() can let it absorb any
    number of trailing arguments of that same kind."""
    kinds = []
    for raw in _split_top_level_args(params_text):
        chunk = raw.strip()
        if not chunk:
            return None
        chunk = chunk.split("=", 1)[0].strip()  # drop a default value
        is_pack = "..." in chunk
        if is_pack:
            chunk = chunk.replace("...", " ")
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if not chunk:
            return None
        first_word = chunk.split(" ", 1)[0]
        if first_word in ("typename", "class"):
            kinds.append(("type", is_pack))
        elif _NONTYPE_PARAM_KEYWORD_RE.match(chunk):
            kinds.append(("nontype", is_pack))
        else:
            return None
    return kinds or None


def _param_kind_at(param_kinds, index: int):
    """Returns the declared (kind, is_pack) for parameter position
    index, letting a TRAILING pack (is_pack=True on the last declared
    parameter) absorb any number of further positions -- or None if
    index is out of range and there's no trailing pack, meaning the
    use provides MORE explicit arguments than this template declares
    at all: never a legitimate instantiation, whatever the arguments'
    own shapes look like."""
    if index < len(param_kinds):
        return param_kinds[index]
    if param_kinds and param_kinds[-1][1]:
        return param_kinds[-1]
    return None


def _split_top_level_args(args_str: str):
    """Splits a template argument-list's raw text on commas at bracket
    depth 0 ONLY -- a nested argument's own internal comma (e.g. the
    one in "Box<int, float>" appearing inside
    "Pair<int, Box<int, float>>") must stay attached to that nested
    argument, not be treated as separating two of the OUTER list's
    arguments."""
    parts = []
    depth = 0
    current = []
    for c in args_str:
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(c)
    parts.append("".join(current))
    return parts


def _normalize_arg(arg: str, template_kinds: dict):
    """Validates and normalizes ONE template argument -- either a leaf
    (a plain type/literal, see _TEMPLATE_ARG_SHAPE_RE) or a nested
    template instantiation (recursing through this same machinery,
    checked against ITS OWN declared parameter kinds via
    template_kinds -- see _normalize_arg_list). Returns the argument's
    normalized text (no brackets added yet -- the caller wraps it), or
    None to abstain: this argument's shape isn't one this scanner
    trusts, so the WHOLE enclosing instantiation is abandoned too (see
    _normalize_arg_list), never partially guessed at. template_kinds
    maps a KNOWN template's name to its _classify_template_params()
    result (or None if that template's own parameter kinds couldn't be
    confidently determined) -- a name absent from it entirely (e.g.
    `std::vector` as a nested argument, never itself discovered as a
    local template declaration) is treated the same as None: no
    kind-matching for arguments nested inside it, same as before this
    per-parameter-kind check existed."""
    arg = arg.strip()
    if not arg:
        return None
    head = _NESTED_ARG_HEAD_RE.match(arg)
    if head is None:
        if _TEMPLATE_ARG_SHAPE_RE.match(arg):
            return re.sub(r"\s+", " ", arg)
        return None
    result = _find_balanced_template_args(arg, head.end() - 1)
    if result is None:
        return None
    inner_text, end = result
    if end != len(arg):
        # Trailing text after the nested instantiation's matching ">"
        # inside this one argument slot (e.g. "Box<int>*", "Box<int> x")
        # -- not a clean nested instantiation by itself, abstain rather
        # than guess which part of it is real.
        return None
    nested_name = head.group(1)
    inner = _normalize_arg_list(inner_text, template_kinds, template_kinds.get(nested_name))
    if inner is None:
        return None
    return f"{nested_name}<{inner}>"


def _normalize_arg_list(args_str: str, template_kinds: dict, param_kinds=None):
    """Validates and normalizes every top-level argument in args_str
    (see _split_top_level_args), or returns None if any single one
    doesn't confidently resolve -- one bad argument abstains the whole
    instantiation, never a partial guess.

    param_kinds, if given (see _classify_template_params()), is the
    enclosing template's own declared parameter kinds -- when present,
    each argument's ACTUAL kind (_arg_kind(): "type" or "nontype") must
    match the kind DECLARED at that position (_param_kind_at()), or the
    whole instantiation is abandoned. This is what rejects
    "Box < 5 > threshold" for `template <typename T> struct Box`: "5"
    passes the plain shape check (_TEMPLATE_ARG_SHAPE_RE) but its kind
    ("nontype") doesn't match the declared parameter's kind ("type") --
    no C++ overload resolution or local shadowing can ever make an
    integer literal a valid argument for a `typename` parameter, so
    this is a correct rejection, never an overcautious guess. When
    param_kinds is None (an unclassifiable or unknown template), no
    kind-matching happens -- same permissive, shape-only behavior as
    before this check existed."""
    parts = _split_top_level_args(args_str)
    args = []
    for i, raw in enumerate(parts):
        norm = _normalize_arg(raw, template_kinds)
        if norm is None:
            return None
        if param_kinds is not None:
            slot = _param_kind_at(param_kinds, i)
            if slot is None or _arg_kind(norm) != slot[0]:
                return None
        args.append(norm)
    if not args:
        return None
    return ", ".join(args)


def _close_adjacent_angle_brackets(spelling: str) -> str:
    """GCC's DWARF type-name spelling for a nested template
    instantiation inserts a space between any two adjacent closing
    "<...>" brackets -- "Box<Box<int>>" is spelled "Box<Box<int> >" in
    DWARF, "Box<Box<Box<int>>>" is "Box<Box<Box<int> > >" -- a
    leftover of the pre-C++11 rule against ">>" being lexed as the
    shift operator, which GCC's internal type printer still follows
    even though the SOURCE code (and this tool's own bracket-depth
    scanner) accepts ">>" directly. Verified empirically for 2 and 3
    levels of nesting and for multi-argument templates (see
    docs/adr/0013). Every ">" this tool ever assembles comes from a
    real closing bracket (a leaf argument can't itself contain "<" or
    ">", see _TEMPLATE_ARG_SHAPE_RE), so it's always correct to insert
    a space wherever two of them are adjacent, anywhere in the
    string -- not just at the very end."""
    while ">>" in spelling:
        spelling = spelling.replace(">>", "> >", 1)
    return spelling


def _normalize_template_instantiation(name: str, args_str: str, template_kinds: dict):
    """Returns the canonical spelling GCC uses in DWARF for a template
    use's raw argument text (no space after "<", exactly one space
    after each comma, and see _close_adjacent_angle_brackets() for
    nested closing brackets), or None if any argument -- at any nesting
    depth -- doesn't look like a plausible type/value FOR THE
    PARAMETER DECLARED AT THAT POSITION (see _normalize_arg_list): a
    stricter, no-cost improvement over checking each argument's shape
    in isolation, since it's what actually resolves the
    "Box < 5 > threshold" ambiguity (see docs/adr/0013's "Fixed
    bugs")."""
    args = _normalize_arg_list(args_str, template_kinds, template_kinds.get(name))
    if args is None:
        return None
    return _close_adjacent_angle_brackets(f"{name}<{args}>")


def _scan_declarations(source_path: str, _visited=None, _texts=None, _template_headers=None):
    """Recursive core of discover_type_names(): scans source_path, and
    every LOCAL ("...") header it #includes (transitively), for
    top-level struct/class declarations. System/library (<...>)
    includes are never followed. Returns (names, template_names) --
    template_names are tracked separately, not touch-instantiated
    directly (see _TEMPLATE_HEADER_RE) -- and _texts/_template_headers
    (out-parameter dicts, if given) accumulate, respectively, each
    visited file's comment/string-stripped text (keyed by resolved
    path, so a caller can search the whole file set again for template
    USES without re-reading anything from disk) and each discovered
    template's raw parameter-list text (keyed by name, first
    occurrence wins -- for _classify_template_params())."""
    if _visited is None:
        _visited = set()
    path = Path(source_path).resolve()
    if path in _visited or not path.is_file():
        return [], []
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
    if _texts is not None:
        _texts[path] = text

    names = []
    template_names = []
    seen = set()
    seen_templates = set()
    for m in TYPE_DECL_RE.finditer(text):
        if m.group("enum"):
            continue
        name = m.group("name")
        header_m = _TEMPLATE_HEADER_RE.search(text[:m.start()])
        if header_m:
            if name not in seen_templates:
                seen_templates.add(name)
                template_names.append(name)
                if _template_headers is not None:
                    _template_headers[name] = header_m.group(1)
            continue
        if name not in seen:
            seen.add(name)
            names.append(name)

    for m in LOCAL_INCLUDE_RE.finditer(comments_stripped):
        included = (path.parent / m.group(1)).resolve()
        inc_names, inc_templates = _scan_declarations(
            str(included), _visited, _texts, _template_headers
        )
        for name in inc_names:
            if name not in seen:
                seen.add(name)
                names.append(name)
        for name in inc_templates:
            if name not in seen_templates:
                seen_templates.add(name)
                template_names.append(name)

    return names, template_names


def discover_type_names(source_path: str, _visited=None):
    """Scans source_path, and every LOCAL ("...") header it #includes
    (transitively), for top-level struct/class declarations. System/
    library (<...>) includes are never followed. A type declared
    anywhere in this file set -- main.cpp itself, or a header it pulls
    in -- is discovered without needing to be listed anywhere.

    A template class declaration alone (e.g. "template <typename T>
    struct Box {...};") can't be touch-instantiated -- there's no
    template argument to fill in. Instead, once every file in the set
    has been scanned for declarations, the SAME file set is searched
    again for actual USES of each discovered template name (e.g.
    "Box<int> value;" appearing anywhere in that file set) --
    real instantiations, since a type that's never actually used
    nowhere exists to reflect anyway. Each distinct, plausible
    instantiation (see _normalize_template_instantiation), INCLUDING
    one used only as another instantiation's own argument (e.g.
    "Box<int>" inside "Pair<int, Box<int>>" -- both are discovered and
    touched, as two separate types), is appended to the returned name
    list in its canonical spelling, matching how GCC names it in
    DWARF. A use this scanner can't confidently parse (an argument that
    doesn't look like a type, literal, or nested instantiation of a
    plausible shape FOR THE PARAMETER DECLARED AT THAT POSITION -- see
    _classify_template_params()) is skipped, not guessed at."""
    visited = set() if _visited is None else _visited
    texts = {}
    template_headers = {}
    names, template_names = _scan_declarations(source_path, visited, texts, template_headers)
    if not template_names:
        return names

    template_kinds = {
        name: _classify_template_params(template_headers.get(name, ""))
        for name in template_names
    }

    seen = set(names)
    for template_name in template_names:
        use_re = _template_use_re(template_name)
        seen_instantiations = set()
        for text in texts.values():
            for m in use_re.finditer(text):
                result = _find_balanced_template_args(text, m.end() - 1)
                if result is None:
                    continue
                args_text, _end = result
                instantiation = _normalize_template_instantiation(
                    template_name, args_text, template_kinds
                )
                if instantiation is None or instantiation in seen_instantiations:
                    continue
                seen_instantiations.add(instantiation)
                if instantiation not in seen:
                    seen.add(instantiation)
                    names.append(instantiation)
    return names


def _sanitize_identifier(name: str) -> str:
    """Turns a type name that isn't necessarily a valid C++ identifier
    by itself -- a template instantiation like "Box<int>" -- into one
    that is, for the driver's own internal Touch_/touch_/NeverCalled_
    wrapper symbol names below. Never used for the type itself (which
    keeps its real spelling, e.g. "Box<int>", everywhere it's actually
    used as a type)."""
    return re.sub(r"[^0-9A-Za-z_]", "_", name)


def emit_driver(source_path: str, output_path: Path):
    source_abs = str(Path(source_path).resolve())
    type_names = discover_type_names(source_path)
    lines = [f'#include "{source_abs}"', ""]
    if type_names:
        lines.append("#include <type_traits>")
        lines.append("")
        lines.append("namespace reflect_dwarf_extraction_touch {")
        lines.append("")
        # A type that (directly or transitively) inherits from a class
        # with a virtual function does NOT get full DWARF just from
        # being a union member below -- verified empirically: GCC only
        # emits a DW_AT_declaration stub for it (byte_size 0, no
        # members) unless its constructor is actually CALLED somewhere
        # in compiled code (even genuinely unreachable code still gets
        # compiled). Calling the real constructor would need real
        # constructor arguments, which defeats the whole point of the
        # union trick below (needed for a type with no default
        # constructor). Calling the DESTRUCTOR instead needs none --
        # explicitly destroying the union member in a function that's
        # never called forces the exact same full emission, verified
        # for a type with both a required-argument constructor AND a
        # virtual base. is_destructible_v guards types with a deleted
        # or inaccessible destructor (rare, but a real edge case) so
        # this never turns a type that used to compile into a hard
        # error.
        lines.append("template <typename T>")
        lines.append("void ForceFullDwarf(T& obj) {")
        lines.append("    if constexpr (std::is_destructible_v<T>) {")
        lines.append("        obj.~T();")
        lines.append("    }")
        lines.append("}")
        lines.append("")
        seen_idents = set()
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
            #
            # ident is a sanitized identifier for the wrapper's OWN
            # symbol names only -- name itself (used below wherever the
            # real type is needed) may not be a valid identifier, e.g.
            # a template instantiation like "Box<int>" (see
            # discover_type_names()).
            ident = _sanitize_identifier(name)
            if ident in seen_idents:
                ident = f"{ident}_{len(seen_idents)}"
            seen_idents.add(ident)
            lines.append(f"union Touch_{ident} {{")
            lines.append(f"    {name} value;")
            lines.append("    char dummy;")
            lines.append(f"    Touch_{ident}() : dummy(0) {{}}")
            lines.append(f"    ~Touch_{ident}() {{}}")
            lines.append("};")
            lines.append(f"Touch_{ident} touch_{ident};")
            lines.append(f"void NeverCalled_{ident}() {{ ForceFullDwarf(touch_{ident}.value); }}")
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
    """objdump sometimes wraps a name as
    "(indirect string, offset: 0x...): <name>" -- strip that prefix by
    finding the literal "): " delimiter that ends it, NOT by splitting
    on the last ":" in the whole string. The real <name> can itself
    contain "::" (any namespace-qualified type, e.g.
    "basic_string<char, std::char_traits<char>, std::allocator<char> >"
    for std::string) -- rsplit(":", 1) used to grab whatever followed
    the LAST "::" inside the name instead of the actual name, silently
    truncating it (e.g. to "allocator<char> >"). Verified against a
    real std::vector<int>/std::string member -- see
    docs/adr/0013-dwarf-based-reflection-generation.md."""
    raw = raw.strip()
    if raw.startswith("("):
        marker = "): "
        idx = raw.find(marker)
        if idx != -1:
            return raw[idx + len(marker):].strip()
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


def _array_dimensions(array_offset, dies, offset_to_index):
    """Returns the dimension sizes of a DW_TAG_array_type DIE at
    array_offset (e.g. [3] for int[3], [3, 4] for int[3][4]), read from
    its direct DW_TAG_subrange_type children -- DW_AT_count if present,
    else DW_AT_upper_bound (0-based, so +1). Returns None if any
    dimension's size can't be determined (e.g. an unbounded array),
    so the caller can abstain instead of guessing."""
    idx = offset_to_index.get(array_offset)
    if idx is None:
        return None
    depth = dies[idx]["depth"]
    dims = []
    j = idx + 1
    while j < len(dies) and dies[j]["depth"] > depth:
        child = dies[j]
        if child["depth"] == depth + 1 and child["tag"] == "DW_TAG_subrange_type":
            attrs = child["attrs"]
            try:
                if "DW_AT_count" in attrs:
                    dims.append(int(attrs["DW_AT_count"], 0))
                elif "DW_AT_upper_bound" in attrs:
                    dims.append(int(attrs["DW_AT_upper_bound"], 0) + 1)
                else:
                    return None
            except ValueError:
                return None
        j += 1
    return dims if dims else None


def resolve_type(offset, dies, by_offset, offset_to_index, _seen=None):
    """Returns (type_name, byte_size, count) for a DW_AT_type reference,
    unwrapping const/volatile/typedef qualifiers. count is 1 for
    everything except a fixed-size array, where it's the real element
    count (see below) -- this is what lets REFLECT_DWARF_MEMBER's
    Count argument be correct instead of the historical hardcoded 1.
    Pointers are named "<inner>*" without recursing into the pointee's
    members (matches docs/adr/0004's opaque-leaf policy for pointers).
    A fixed-size array resolves to "<elem>[N]" (or "<elem>[N][M]" for
    multiple dimensions) with the correct total byte size and total
    element count -- GCC does not reliably emit DW_AT_byte_size on the
    array type DIE itself, so both are computed from the element type's
    size times each DW_TAG_subrange_type child's count via
    _array_dimensions(). (This used to fall through to the generic
    branch below, which has no DW_AT_name for an array type DIE and so
    silently returned ("<unknown>", 0) -- a real fixed-size array
    member's SIZE, not just its name, reported as 0; see docs/adr/0013's
    "Known open risks" for how this was found.) Anything unresolvable --
    including an array whose dimension can't be determined -- becomes
    ("<unknown>", 0, 0) rather than a guess; find_type() treats that
    sentinel as "skip this member, don't emit wrong data"."""
    if _seen is None:
        _seen = set()
    if offset is None or offset in _seen:
        return ("<unknown>", 0, 0)
    _seen.add(offset)
    die = by_offset.get(offset)
    if die is None:
        return ("<unknown>", 0, 0)
    tag = die["tag"]
    attrs = die["attrs"]
    if tag == "DW_TAG_base_type" or tag in TYPE_DIE_TAGS:
        name = parse_name(attrs.get("DW_AT_name", "<unknown>"))
        size = int(attrs.get("DW_AT_byte_size", "0") or 0)
        return (name, size, 1)
    if tag == "DW_TAG_pointer_type":
        inner_name, _, _ = resolve_type(
            parse_ref(attrs.get("DW_AT_type", "")), dies, by_offset, offset_to_index, _seen
        )
        return (f"{inner_name}*", 8, 1)
    if tag == "DW_TAG_array_type":
        elem_name, elem_size, _ = resolve_type(
            parse_ref(attrs.get("DW_AT_type", "")), dies, by_offset, offset_to_index, _seen
        )
        dims = _array_dimensions(offset, dies, offset_to_index)
        if elem_name == "<unknown>" or elem_size == 0 or dims is None:
            return ("<unknown>", 0, 0)
        total_count = 1
        for d in dims:
            total_count *= d
        suffix = "".join(f"[{d}]" for d in dims)
        return (f"{elem_name}{suffix}", elem_size * total_count, total_count)
    if tag in ("DW_TAG_const_type", "DW_TAG_volatile_type", "DW_TAG_typedef"):
        inner_ref = parse_ref(attrs.get("DW_AT_type", ""))
        if inner_ref is None:
            return ("void", 0, 1)
        return resolve_type(inner_ref, dies, by_offset, offset_to_index, _seen)
    name = parse_name(attrs.get("DW_AT_name", "<unknown>"))
    size = int(attrs.get("DW_AT_byte_size", "0") or 0)
    return (name, size, 1)


def find_type(type_name: str, dies, by_offset):
    """Returns (byte_size, [(member_name, member_type, offset, size, count), ...], skipped_names)
    for the first structure/class DIE named type_name, or None if not
    found. Only DIRECT DW_TAG_member children are collected -- methods,
    constructors, and nested types (any other tag) are skipped, and
    grandchildren (e.g. a constructor's formal parameters) are walked
    past via depth tracking without being mistaken for members. A
    member whose type resolve_type() couldn't confidently resolve (its
    "<unknown>" sentinel) is left out of the member list entirely --
    its name is returned in skipped_names instead, so the caller can
    note it was omitted rather than silently emit wrong offset/size
    data for it.

    A same-named DIE carrying DW_AT_declaration (an incomplete
    forward-declaration stub -- no members, no real byte_size) is
    skipped in favor of a later, real definition: a type can be
    forward-declared (e.g. as a pointer's pointee, or -- see
    docs/adr/0013's virtual-base-class fix -- before the compiler
    decides to emit its full definition at all) anywhere earlier in
    the same object than its actual full DW_TAG_structure_type/
    DW_TAG_class_type DIE. Returning the first tag/name match
    unconditionally used to silently return the incomplete stub (zero
    members, byte_size 0) as if it were the real type.

    A member named "_vptr.<Class>" -- GCC's compiler-generated vtable
    pointer for any class with a virtual function -- is excluded
    entirely, not returned in either the member list or skipped_names:
    it was never a declared data member, so it isn't "resolved" or
    "skipped", it's simply not reflectable data. See docs/adr/0013's
    "Fixed bugs"."""
    offset_to_index = {d["offset"]: i for i, d in enumerate(dies)}
    for i, die in enumerate(dies):
        if die["tag"] not in TYPE_DIE_TAGS:
            continue
        name_attr = die["attrs"].get("DW_AT_name")
        if name_attr is None or parse_name(name_attr) != type_name:
            continue
        if die["attrs"].get("DW_AT_declaration"):
            continue
        depth = die["depth"]
        byte_size = int(die["attrs"].get("DW_AT_byte_size", "0") or 0)
        members = []
        skipped = []
        j = i + 1
        while j < len(dies) and dies[j]["depth"] > depth:
            child = dies[j]
            if child["depth"] == depth + 1 and child["tag"] == "DW_TAG_member":
                mname = parse_name(child["attrs"].get("DW_AT_name", ""))
                moffset = int(child["attrs"].get("DW_AT_data_member_location", "0") or 0)
                type_ref = parse_ref(child["attrs"].get("DW_AT_type", ""))
                mtype, msize, mcount = resolve_type(type_ref, dies, by_offset, offset_to_index)
                if mname:
                    if mname.startswith("_vptr."):
                        # GCC's compiler-generated vtable pointer, not
                        # a declared data member -- excluded entirely,
                        # not "skipped" (this isn't uncertainty about a
                        # real member, it's a categorical exclusion of
                        # something that was never a user field). See
                        # docs/adr/0013's "Fixed bugs" for how this was
                        # found.
                        pass
                    elif mtype == "<unknown>":
                        skipped.append(mname)
                    else:
                        members.append((mname, mtype, moffset, msize, mcount))
            j += 1
        return byte_size, members, skipped
    return None


def _skip_warning(message: str) -> str:
    """Returns a "#warning <message>" preprocessor directive line. A
    type or member DWARF couldn't confidently resolve (see extract())
    is correctly left out of the generated registration rather than
    guessed at, but leaving *only* a `//` comment behind meant nothing
    ever surfaced that at build time -- easy to miss in a generated
    header nobody reads. Emitting a real #warning instead makes every
    build that #includes the generated header print it, without
    failing the build (same "abstain, never guess, never break the
    build" policy as everything else this tool does). #warning is a
    non-standard but essentially universal GCC/Clang extension --
    QNX's qcc/aarch64-unknown-nto-qnx8.0.0-g++ front end is GCC-based
    and supports it too (see docs/adr/0013's "Fixed bugs")."""
    return f"#warning {message}"


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
            lines.append(_skip_warning(f"{type_name}: not found in DWARF info -- entire type skipped, not guessed."))
            continue
        byte_size, members, skipped = result
        # Type is REFLECT_DWARF_CLASS_BEGIN's trailing variadic
        # argument, not its first, specifically so a template
        # instantiation's top-level comma (e.g. "Pair<int, float>")
        # doesn't get misparsed as an extra macro argument by the
        # preprocessor -- see src/ReflectionMacros.hpp's comment.
        lines.append(f'REFLECT_DWARF_CLASS_BEGIN({byte_size}, "{type_name}", {type_name})')
        for mname, mtype, moffset, msize, mcount in members:
            lines.append(
                f'    REFLECT_DWARF_MEMBER("{mname}", "{mtype}", {moffset}, {msize}, {mcount})'
            )
        for mname in skipped:
            lines.append(
                f"    // {mname}: type not resolved in DWARF info -- skipped, not guessed."
            )
            lines.append(
                _skip_warning(f"{type_name}::{mname}: type not resolved in DWARF info -- member skipped, not guessed.")
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
