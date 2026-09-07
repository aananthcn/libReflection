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

    def test_driver_with_no_types_has_no_touch_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.cpp"
            source.write_text("int main() { return 0; }")
            output = Path(tmp) / "driver.cpp"
            gen.emit_driver(str(source), output)
            content = output.read_text()
        self.assertNotIn("reflect_dwarf_extraction_touch", content)


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
        self.assertIn("REFLECT_DWARF_CLASS_BEGIN(Vec3, 12)", out)
        self.assertIn('REFLECT_DWARF_MEMBER("x", "float", 0, 4)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("y", "float", 4, 4)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("z", "float", 8, 4)', out)

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
        self.assertIn("REFLECT_DWARF_CLASS_BEGIN(Encapsulated, 8)", out)
        self.assertIn('REFLECT_DWARF_MEMBER("x_", "int", 0, 4)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("y_", "float", 4, 4)', out)

    def test_non_aggregate_with_method_resolves(self):
        out = self._extract(
            "class Counter {\n"
            "public:\n"
            "    void Increment() { ++count; }\n"
            "    int count = 0;\n"
            "};\n"
        )
        self.assertIn("REFLECT_DWARF_CLASS_BEGIN(Counter, 4)", out)
        self.assertIn('REFLECT_DWARF_MEMBER("count", "int", 0, 4)', out)

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
        self.assertIn("REFLECT_DWARF_CLASS_BEGIN(RequiresArgs, 4)", out)
        self.assertIn('REFLECT_DWARF_MEMBER("value_", "int", 0, 4)', out)

    def test_alignment_padding_matches_real_layout(self):
        # double then char forces padding -- the generated offset must
        # match the REAL compiled layout, not a naive sum of sizes.
        out = self._extract("struct Widget { double weight; char code; };")
        self.assertIn('REFLECT_DWARF_MEMBER("weight", "double", 0, 8)', out)
        self.assertIn('REFLECT_DWARF_MEMBER("code", "char", 8, 1)', out)

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


if __name__ == "__main__":
    unittest.main()
