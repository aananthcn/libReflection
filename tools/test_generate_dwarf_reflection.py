#!/usr/bin/env python3
"""Tests for generate_dwarf_reflection.py.

Two kinds of test here:
  - Pure text-scanning tests (discover_type_names, driver emission) --
    fast, no compiler needed.
  - End-to-end tests that actually compile a fixture with a real
    compiler, extract its DWARF, and check the generated registration
    -- these are the ones that matter most, since the whole point of
    this tool is what a real compiler's debug info says, not what a
    hand-written mock of it would say. Skipped if g++/objdump aren't
    on PATH (e.g. a constrained CI image).
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_dwarf_reflection as gen  # noqa: E402


def has_toolchain():
    return shutil.which("g++") is not None and shutil.which("objdump") is not None


class TestDiscoverTypeNames(unittest.TestCase):
    def _run(self, source: str, filename: str = "test.cpp"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / filename
            path.write_text(source)
            return gen.discover_type_names(str(path))

    def test_finds_struct_and_class(self):
        names = self._run("struct A { int x; }; class B { int y; };")
        self.assertEqual(names, ["A", "B"])

    def test_ignores_declaration_inside_string_literal(self):
        # Real bug caught during development: a log message like
        # "class name: X" was misparsed as a type declaration.
        names = self._run('void f() { std::cout << "class name: X"; }')
        self.assertEqual(names, [])

    def test_ignores_declaration_inside_comment(self):
        names = self._run("// struct Fake { int a; };\nstruct Real { int b; };")
        self.assertEqual(names, ["Real"])

    def test_follows_local_quoted_include(self):
        with tempfile.TemporaryDirectory() as tmp:
            header = Path(tmp) / "Types.hpp"
            header.write_text("struct FromHeader { int a; };")
            main = Path(tmp) / "main.cpp"
            main.write_text('#include "Types.hpp"\nstruct FromMain { int b; };')
            names = gen.discover_type_names(str(main))
        self.assertIn("FromHeader", names)
        self.assertIn("FromMain", names)

    def test_does_not_follow_angle_bracket_include(self):
        names = self._run("#include <vector>\nstruct A { int a; };")
        self.assertEqual(names, ["A"])

    def test_deduplicates(self):
        names = self._run("struct A { int a; }; void f(); struct A;")
        self.assertEqual(names, ["A"])

    def test_excludes_template_declarations(self):
        # A bare template name can't be safely touch-instantiated (no
        # template arguments are known) -- generating "Box touch_Box;"
        # for "template <typename T> struct Box { T value; };" is a
        # compile error, not something to attempt.
        names = self._run(
            "template <typename T> struct Box { T value; };\n"
            "struct Real { int a; };\n"
        )
        self.assertEqual(names, ["Real"])

    def test_finds_template_instantiation_used_in_source(self):
        # Regression test (see docs/adr/0013): a template class is never
        # touch-instantiated by its bare declaration alone (no template
        # argument is known there), but an actual USE of it elsewhere in
        # the source -- e.g. "Box<int> instance;" -- names a real,
        # concrete type that DOES exist in the compiled program, so it's
        # discovered and touched via its real, canonical spelling.
        names = self._run(
            "template <typename T> struct Box { T value; };\n"
            "Box<int> instance;\n"
        )
        self.assertEqual(names, ["Box<int>"])

    def test_finds_multi_argument_template_instantiation(self):
        # A multi-argument instantiation's canonical spelling has a
        # top-level comma ("Pair<int, float>") -- this is exactly the
        # shape that broke REFLECT_DWARF_CLASS_BEGIN's old (Type, Size)
        # argument order (the C preprocessor doesn't know "<...>"
        # protects a comma the way "(...)" does); Type is now the
        # trailing variadic argument specifically to survive this.
        names = self._run(
            "template <typename A, typename B> struct Pair { A first; B second; };\n"
            "Pair<int, float> instance;\n"
        )
        self.assertEqual(names, ["Pair<int, float>"])

    def test_normalizes_instantiation_spacing_variants(self):
        # "Pair<int,float>" and "Pair< int , float >" name the exact
        # same type -- both must normalize to GCC's canonical DWARF
        # spelling ("Pair<int, float>", no space after "<"/before ">",
        # exactly one space after the comma) so find_type()'s later
        # exact-string lookup actually matches, and so the two uses
        # aren't (wrongly) treated as two different types to touch.
        names = self._run(
            "template <typename A, typename B> struct Pair { A first; B second; };\n"
            "Pair<int,float> a;\n"
            "Pair< int , float > b;\n"
        )
        self.assertEqual(names, ["Pair<int, float>"])

    def test_abstains_on_the_outer_layer_of_a_nested_instantiation(self):
        # "Box<Box<int>>" as a WHOLE is never captured -- this scanner
        # never parses balanced nested "<...>", only a single,
        # non-nested argument list, so the outer instantiation is
        # abstained on rather than guessed at. The regex incidentally
        # still matches the INNER "Box<int>" on its own, though (it
        # reads as a plain, non-nested instantiation by itself) -- and
        # that's a real, independently resolvable type, so finding it
        # is correct, not a bug, even though it isn't a promise this
        # scanner makes for every nested case.
        names = self._run(
            "template <typename T> struct Box { T value; };\n"
            "Box<Box<int>> nested;\n"
        )
        self.assertEqual(names, ["Box<int>"])

    def test_abstains_on_implausible_template_argument(self):
        # Defense against emitting an instantiation that can't possibly
        # compile: an argument that doesn't look like a type name or an
        # integer literal (see _TEMPLATE_ARG_SHAPE_RE) -- here, a
        # floating-point literal -- is abstained on, not guessed at.
        names = self._run(
            "template <typename T> struct Box { T value; };\n"
            "Box<3.14> floating_point_arg;\n"
        )
        self.assertEqual(names, [])

    def test_known_residual_risk_of_bare_integer_comparison(self):
        # Documented, accepted residual risk (see docs/adr/0013): a
        # chained relational comparison shaped exactly like a
        # single-argument template use with an integer-literal argument
        # ("Box < 5 > threshold") is indistinguishable from a genuine
        # non-type template instantiation "Box<5>" by text alone. This
        # test exists to make that trade-off explicit and testable, not
        # to assert it's fine to leave forever -- a real occurrence of
        # this shape would surface as a hard, loud compile error in the
        # generated driver (a name that isn't actually a template
        # instantiation fails to compile), never as silently wrong
        # reflection data.
        names = self._run(
            "template <typename T> struct Box { T value; };\n"
            "void f(int Box, int threshold) { if (Box < 5 > threshold) {} }\n"
        )
        self.assertEqual(names, ["Box<5>"])


class TestEmitDriver(unittest.TestCase):
    def test_driver_includes_source_and_touches_each_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.cpp"
            source.write_text("struct A { int a; }; class B { int b; };")
            output = Path(tmp) / "driver.cpp"
            gen.emit_driver(str(source), output)
            content = output.read_text()
        self.assertIn(f'#include "{source.resolve()}"', content)
        # Touched via a wrapper union (works for non-default-
        # constructible types too -- see
        # TestEndToEndExtraction.test_driver_touch_works_for_non_default_constructible_type),
        # not a bare variable.
        self.assertIn("A value;", content)
        self.assertIn("Touch_A touch_A;", content)
        self.assertIn("B value;", content)
        self.assertIn("Touch_B touch_B;", content)
        # Regression test for the virtual-base-class bug (see
        # docs/adr/0013): a type inheriting from a polymorphic base
        # doesn't get full DWARF just from being a union member --
        # its destructor must actually be called somewhere in compiled
        # code (even unreachable code). NeverCalled_<Type> calling
        # ForceFullDwarf forces exactly that, without ever needing to
        # know a constructor's arguments.
        self.assertIn("template <typename T>", content)
        self.assertIn("void ForceFullDwarf(T& obj)", content)
        self.assertIn("void NeverCalled_A() { ForceFullDwarf(touch_A.value); }", content)
        self.assertIn("void NeverCalled_B() { ForceFullDwarf(touch_B.value); }", content)

    def test_driver_with_no_types_has_no_touch_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.cpp"
            source.write_text("int main() { return 0; }")
            output = Path(tmp) / "driver.cpp"
            gen.emit_driver(str(source), output)
            content = output.read_text()
        self.assertNotIn("reflect_dwarf_extraction_touch", content)


class TestParseName(unittest.TestCase):
    def test_plain_name_unwrapped(self):
        self.assertEqual(gen.parse_name("PoorPoint"), "PoorPoint")

    def test_indirect_string_prefix_is_stripped(self):
        self.assertEqual(
            gen.parse_name("(indirect string, offset: 0x123): PoorPoint"), "PoorPoint"
        )

    def test_namespace_qualified_name_is_not_truncated(self):
        # Regression test for a real bug: rsplit(":", 1) used to grab
        # everything after the LAST ":" in the whole string, which for
        # a namespace-qualified name (containing "::") lands INSIDE the
        # name itself, not at the intended "(indirect string, ...): "
        # prefix boundary.
        raw = (
            "(indirect string, offset: 0x26c6): "
            "basic_string<char, std::char_traits<char>, std::allocator<char> >"
        )
        self.assertEqual(
            gen.parse_name(raw),
            "basic_string<char, std::char_traits<char>, std::allocator<char> >",
        )


@unittest.skipUnless(has_toolchain(), "requires g++ and objdump on PATH")
class TestEndToEndExtraction(unittest.TestCase):
    def _extract(self, source_text: str) -> str:
        """Compiles source_text through the real driver+extraction
        pipeline and returns the generated header's text. The temp
        directory is cleaned up via addCleanup (not a `with` block)
        so it -- and self.last_object/self.last_source, set here for
        tests that need to probe the compiled object further -- stay
        alive for the rest of the test method, not just this call."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        tmp_path = Path(tmp)

        source = tmp_path / "fixture.cpp"
        source.write_text(source_text)

        driver = tmp_path / "driver.cpp"
        gen.emit_driver(str(source), driver)

        obj = tmp_path / "driver.o"
        subprocess.run(
            ["g++", "-std=c++20", "-g", "-gdwarf-4", "-c", str(driver), "-o", str(obj)],
            check=True, capture_output=True,
        )
        self.last_object = str(obj)
        self.last_source = str(source)

        output = tmp_path / "out.hpp"
        gen.extract(str(obj), str(source), output)
        return output.read_text()

    def test_public_struct_resolves_correctly(self):
        out = self._extract("struct Vec3 { float x; float y; float z; };")
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(12, "Vec3", Vec3)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("x", "float", 0, 4, 1)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("y", "float", 4, 4, 1)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("z", "float", 8, 4, 1)', out)

    def test_private_members_resolve_with_correct_offsets(self):
        # The entire point of this tool: DWARF exposes private members,
        # which no source-text-based mechanism (this project tried and
        # reverted one -- see docs/adr/0012) can reach without an
        # intrusive friend declaration.
        out = self._extract(
            "class Encapsulated {\n"
            "public:\n"
            "    Encapsulated(int x, int y) : x_(x), y_(y) {}\n"
            "private:\n"
            "    int x_;\n"
            "    float y_;\n"
            "};\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(8, "Encapsulated", Encapsulated)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("x_", "int", 0, 4, 1)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("y_", "float", 4, 4, 1)', out)

    def test_non_aggregate_with_method_resolves(self):
        out = self._extract(
            "class Counter {\n"
            "public:\n"
            "    void Increment() { ++count; }\n"
            "    int count = 0;\n"
            "};\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(4, "Counter", Counter)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("count", "int", 0, 4, 1)', out)

    def test_driver_touch_works_for_non_default_constructible_type(self):
        # This is the exact case a plain "Type touch_Type;" fails to
        # compile for -- a class whose only constructor takes
        # arguments (the common shape for encapsulated types, i.e.
        # the entire reason this tool exists). Reaching the assertions
        # at all (no CalledProcessError from the driver failing to
        # compile) is itself part of what's being tested.
        out = self._extract(
            "class RequiresArgs {\n"
            "public:\n"
            "    explicit RequiresArgs(int v) : value_(v) {}\n"
            "private:\n"
            "    int value_;\n"
            "};\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(4, "RequiresArgs", RequiresArgs)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("value_", "int", 0, 4, 1)', out)

    def test_alignment_padding_matches_real_layout(self):
        # double then char forces padding -- the generated offset must
        # match the REAL compiled layout, not a naive sum of sizes.
        out = self._extract("struct Widget { double weight; char code; };")
        self.assertIn('REFLECT_DWARF_MEMBER("weight", "double", 0, 8, 1)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("code", "char", 8, 1, 1)', out)

    def test_fixed_size_array_member_resolves_with_correct_size(self):
        # Regression test for docs/adr/0013's "Known open risks" bug:
        # resolve_type() had no DW_TAG_array_type case, so an array
        # member silently got ("<unknown>", 0) -- a real member's SIZE
        # reported as 0, not an abstention. Must resolve to the real
        # element type/count and the real total byte size (12, not 0),
        # and the real element COUNT (3), not the historical hardcoded 1.
        out = self._extract("struct WithArray { int values[3]; float f; };")
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(16, "WithArray", WithArray)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("values", "int[3]", 0, 12, 3)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("f", "float", 12, 4, 1)', out)

    def test_multi_dimensional_array_member_resolves(self):
        out = self._extract("struct MultiDim { double grid[2][3]; };")
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(48, "MultiDim", MultiDim)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("grid", "double[2][3]", 0, 48, 6)', out)

    def test_template_instantiation_resolves_correctly(self):
        # Regression test (see docs/adr/0013): a template class used
        # nowhere but declared ("template <typename T> struct Box {...}")
        # used to be entirely unreachable -- no bare-declaration touch
        # is possible without a known argument. A real USE of it in the
        # source, though, names a real, concrete, existing type -- this
        # is now discovered and resolved with zero annotation, just
        # like any non-template type.
        out = self._extract(
            "template <typename T> struct Box { T value; };\n"
            "Box<int> instance;\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(4, "Box<int>", Box<int>)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("value", "int", 0, 4, 1)', out)

    def test_multi_argument_template_instantiation_resolves_correctly(self):
        # The critical case: a multi-argument instantiation's canonical
        # name has a top-level comma ("Pair<int, float>"). Naively
        # emitting REFLECT_DWARF_CLASS_BEGIN(Pair<int, float>, 8) would
        # be misparsed by the C preprocessor as THREE macro arguments,
        # not two -- Type must be the macro's trailing variadic
        # argument specifically so this comma survives intact (see
        # src/ReflectionMacros.hpp). This test fails to compile (not
        # just asserts wrong output) if that regresses.
        out = self._extract(
            "template <typename A, typename B> struct Pair { A first; B second; };\n"
            "Pair<int, float> instance;\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(8, "Pair<int, float>", Pair<int, float>)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("first", "int", 0, 4, 1)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("second", "float", 4, 4, 1)', out)

    def test_std_array_member_resolves_via_its_own_structure_type(self):
        # std::array<T, N> is a real class wrapping a C array internally
        # -- its own DW_TAG_structure_type DIE already carries a real
        # name and byte_size directly, so this needs no special case in
        # resolve_type() beyond the existing structure/class branch
        # (unlike a raw C array member, which points straight at a
        # DW_TAG_array_type DIE and needed the fix above).
        out = self._extract("#include <array>\nstruct Samples { std::array<float, 4> values; };")
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(16, "Samples", Samples)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("values", "array<float, 4>", 0, 16, 1)', out)

    def test_virtual_base_class_resolves_correctly(self):
        # Regression test for a real, serious bug (see docs/adr/0013):
        # GCC never emits a full DW_TAG_structure_type definition for a
        # type inheriting from a polymorphic base when the only touch
        # is a union member that's never actually constructed/destroyed
        # -- only an incomplete DW_AT_declaration stub (byte_size 0, no
        # members). This used to make WithVirtualBase silently resolve
        # to REFLECT_DWARF_CLASS_BEGIN(0, "WithVirtualBase", WithVirtualBase) with NO
        # members at all -- not a compile error, not an abstention,
        # just silently wrong. Also exercises the hardest combination:
        # a virtual base AND a constructor requiring an argument AND a
        # private member, all at once.
        out = self._extract(
            "struct VBase {\n"
            "    virtual ~VBase() {}\n"
            "    virtual void Foo() {}\n"
            "    int base_value;\n"
            "};\n"
            "struct WithVirtualBase : virtual VBase {\n"
            "    explicit WithVirtualBase(int v) : v_(v) {}\n"
            "private:\n"
            "    int v_;\n"
            "};\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(32, "WithVirtualBase", WithVirtualBase)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("v_", "int", 8, 4, 1)', out)
        self.assertNotIn("_vptr", out)

    def test_vtable_pointer_is_excluded_from_members(self):
        # Regression test (see docs/adr/0013's "Fixed bugs"): GCC
        # exposes its own compiler-generated vtable pointer as an
        # ordinary DW_TAG_member named "_vptr.<Class>" for any class
        # with a virtual function. It was never a declared data member
        # and must not show up as one -- only the real member, at its
        # real (vptr-shifted) offset, should be emitted.
        out = self._extract(
            "struct WithVirtualFn {\n"
            "    virtual ~WithVirtualFn() {}\n"
            "    virtual void Foo() {}\n"
            "    int real_value;\n"
            "};\n"
        )
        self.assertIn('REFLECT_DWARF_CLASS_BEGIN(16, "WithVirtualFn", WithVirtualFn)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("real_value", "int", 8, 4, 1)', out)
        self.assertNotIn("_vptr", out)

    def test_namespace_qualified_type_name_is_not_truncated(self):
        # Regression test for a real bug in parse_name(): objdump wraps
        # some DW_AT_name values as
        # "(indirect string, offset: 0x...): <real name>", and the real
        # name of ANY namespace-qualified type (std::vector, std::string,
        # ...) itself contains "::" -- e.g.
        # "vector<int, std::allocator<int> >". parse_name() used to grab
        # everything after the LAST ":" in the whole string (rsplit),
        # which lands inside that "::" and silently truncates the name
        # to "allocator<int> >" instead of stripping only the intended
        # "(indirect string, ...): " prefix.
        out = self._extract(
            "#include <vector>\n#include <string>\n"
            "struct WithContainers { std::vector<int> items; std::string name; };"
        )
        self.assertIn(
            'REFLECT_DWARF_MEMBER("items", "vector<int, std::allocator<int> >", 0, 24, 1)', out
        )
        self.assertIn(
            'REFLECT_DWARF_MEMBER("name", '
            '"basic_string<char, std::char_traits<char>, std::allocator<char> >", 24, 32, 1)',
            out,
        )

    def test_unresolvable_member_is_skipped_not_guessed(self):
        # find_type() must never fall back to emitting resolve_type()'s
        # "<unknown>" sentinel as a literal REFLECT_DWARF_MEMBER -- an
        # unresolvable member is left out and noted in a comment
        # instead (this is what the array-member bug above violated).
        out = self._extract("struct WithArray { int values[3]; float f; };")
        self.assertNotIn('"<unknown>"', out)

    def test_skipped_member_emits_a_build_warning(self):
        # A member correctly left out as unresolvable used to be
        # visible only as a `//` comment inside a generated file
        # nobody reads -- see docs/adr/0013's "silently absent, not
        # loudly flagged" limitation. A flexible array member (a GCC
        # extension, not standard C++, but real code uses it) is the
        # one known real-world case: GCC emits neither DW_AT_count nor
        # DW_AT_upper_bound on its DW_TAG_subrange_type, so
        # _array_dimensions() can't determine a size and resolve_type()
        # abstains. extract() must now ALSO emit a real #warning
        # directive alongside the comment, so a build that #includes
        # the generated header can't miss it.
        out = self._extract("struct WithFlex { int n; int values[]; };")
        self.assertIn(
            "// values: type not resolved in DWARF info -- skipped, not guessed.", out
        )
        self.assertIn(
            "#warning WithFlex::values: type not resolved in DWARF info -- "
            "member skipped, not guessed.",
            out,
        )

    def test_type_not_found_emits_a_build_warning(self):
        # Mirrors test_skipped_member_emits_a_build_warning for the
        # whole-type "not found" path (see
        # test_find_type_returns_none_for_a_name_not_in_dwarf's comment
        # on why this can't be engineered through the real driver --
        # every discovered name is unconditionally touch-instantiated).
        # Compiles an object that never touches Ghost at all, so
        # extract()'s find_type() genuinely can't find it, exercising
        # extract()'s own "not found" branch (not find_type() directly).
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        tmp_path = Path(tmp)
        source = tmp_path / "fixture.cpp"
        source.write_text("struct Ghost { int a; };")
        unrelated = tmp_path / "unrelated.cpp"
        unrelated.write_text("int unrelated_global;")
        obj = tmp_path / "unrelated.o"
        subprocess.run(
            ["g++", "-std=c++20", "-g", "-gdwarf-4", "-c", str(unrelated), "-o", str(obj)],
            check=True, capture_output=True,
        )
        output = tmp_path / "out.hpp"
        gen.extract(str(obj), str(source), output)
        text = output.read_text()
        self.assertIn("// Ghost: not found in DWARF info -- skipped, not guessed.", text)
        self.assertIn(
            "#warning Ghost: not found in DWARF info -- entire type skipped, not guessed.",
            text,
        )

    def test_find_type_returns_none_for_a_name_not_in_dwarf(self):
        # Exercises find_type()'s "not found" path directly against a
        # real compiled object's DWARF, rather than trying to engineer
        # an end-to-end scenario where a discovered-by-text-scan name
        # both compiles as a touch-instance AND is somehow absent from
        # debug info -- not realistic once templates are excluded at
        # discovery (see TestDiscoverTypeNames.test_excludes_template_declarations).
        self._extract("struct Real { int a; };")
        dwarf_text = gen.dump_dwarf(self.last_object)
        dies = gen.parse_dies(dwarf_text)
        by_offset = {d["offset"]: d for d in dies}
        self.assertIsNotNone(gen.find_type("Real", dies, by_offset))
        self.assertIsNone(gen.find_type("DoesNotExist", dies, by_offset))

    def test_find_type_skips_a_declaration_only_stub(self):
        # Defense-in-depth regression test (see docs/adr/0013): a name
        # that only ever appears as an incomplete DW_AT_declaration
        # stub in the DWARF (e.g. a type that's forward-declared and
        # used only via a pointer, never actually defined anywhere)
        # must be treated as "not found", never as a real type with
        # zero members and byte_size 0 -- which is exactly what the
        # virtual-base-class bug looked like before it was fixed.
        self._extract("struct Forward;\nstruct HasPointer { Forward* p; };")
        dwarf_text = gen.dump_dwarf(self.last_object)
        dies = gen.parse_dies(dwarf_text)
        by_offset = {d["offset"]: d for d in dies}
        self.assertIsNone(gen.find_type("Forward", dies, by_offset))


if __name__ == "__main__":
    unittest.main()
