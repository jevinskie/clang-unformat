#!/usr/bin/env python3
# A tool to parse the FormatStyle struct from Format.h and update the
# documentation in ../ClangFormatStyleOptions.rst automatically.
# Run from the directory in which this file is located to update the docs.

import argparse
import inspect
import os
import re
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Self

# import rich
from attrs import Factory, define, field

# from beartype import BeartypeConf
# from beartype.claw import beartype_package, beartype_all, beartype_this_package
# beartype_package("scripts")
# beartype_this_package()
# beartype_all(conf=BeartypeConf(violation_type=UserWarning))

# foo: int = 5
# foo = "bar"


def CLANG_DIR(a: argparse.Namespace) -> Path:
    return a.clang_dir


def FORMAT_STYLE_FILE(a: argparse.Namespace) -> Path:
    return CLANG_DIR(a) / "include/clang/Format/Format.h"


def INCLUDE_STYLE_FILE(a: argparse.Namespace) -> Path:
    return CLANG_DIR(a) / "include/clang/Tooling/Inclusions/IncludeStyle.h"


def PLURALS_FILE(a: argparse.Namespace) -> Path:
    return CLANG_DIR(a) / "docs/tools/plurals.txt"


plurals: set[str] = set()


def register_plural(singular: str, plural: str, args: argparse.Namespace) -> str:
    if plural not in plurals:
        if not hasattr(register_plural, "generated_new_plural"):
            print(
                "Plural generation: you can use "
                f"`git checkout -- {os.path.relpath(PLURALS_FILE(args))}` "
                "to reemit warnings or `git add` to include new plurals\n"
            )
        register_plural.generated_new_plural = True  # type: ignore

        plurals.add(plural)
        with open(PLURALS_FILE(args), "a") as f:
            f.write(plural + "\n")
        cf = inspect.currentframe()
        lineno = ""
        if cf and cf.f_back:
            lineno = ":" + str(cf.f_back.f_lineno)
        print(
            f"{__file__}{lineno} check if plural of {singular} is {plural}",
            file=sys.stderr,
        )
    return plural


def pluralize(word: str, args: argparse.Namespace) -> str:
    lword = word.lower()
    if len(lword) >= 2 and lword[-1] == "y" and lword[-2] not in "aeiou":
        return register_plural(word, word[:-1] + "ies", args)
    elif lword.endswith(("s", "sh", "ch", "x", "z")):
        return register_plural(word, word[:-1] + "es", args)
    elif lword.endswith("fe"):
        return register_plural(word, word[:-2] + "ves", args)
    elif lword.endswith("f") and not lword.endswith("ff"):
        return register_plural(word, word[:-1] + "ves", args)
    else:
        return register_plural(word, word + "s", args)


def to_yaml_type(typestr: str, args: argparse.Namespace) -> str:
    if typestr == "bool":
        return "Boolean"
    elif typestr == "int":
        return "Integer"
    elif typestr == "unsigned":
        return "Unsigned"
    elif typestr == "std::string":
        return "String"

    match = re.match(r"std::vector<(.*)>$", typestr)
    if match:
        return "List of " + pluralize(to_yaml_type(match.group(1), args), args)

    match = re.match(r"std::optional<(.*)>$", typestr)
    if match:
        return to_yaml_type(match.group(1), args)

    return typestr


def doxygen2rst(text: str) -> str:
    text = re.sub(r"<tt>\s*(.*?)\s*<\/tt>", r"``\1``", text)
    text = re.sub(r"\\c ([^ ,;\.]+)", r"``\1``", text)
    text = re.sub(r"\\\w+ ", "", text)
    return text


def indent(text: str, columns: int, indent_first_line: bool = True) -> str:
    indent_str = " " * columns
    s = re.sub(r"\n([^\n])", "\n" + indent_str + "\\1", text, flags=re.S)
    if not indent_first_line or s.startswith("\n"):
        return s
    return indent_str + s


@define(auto_attribs=True, frozen=True)
class Type:
    cxx_name: str
    yaml_name: str
    is_list: bool
    is_optional: bool
    is_deprecated: bool

    @classmethod
    def from_cxx(cls, cxx_name: str, args: argparse.Namespace, is_deprecated: bool = False) -> Self:
        return cls(
            cxx_name,
            to_yaml_type(cxx_name, args),
            cxx_name.startswith("std::vector"),
            cxx_name.startswith("std::optional"),
            is_deprecated,
        )


@define(auto_attribs=True, frozen=True)
class Version:
    major: int
    minor: int | None

    @classmethod
    def from_opt_str(cls, vstr: str | None) -> Self | None:
        if vstr is None:
            return None
        sp = vstr.split(".")
        if len(sp) == 1:
            return cls(int(sp[0]), None)
        elif len(sp) == 2:
            return cls(int(sp[0]), int(sp[1]))
        else:
            raise ValueError(f"can't parse version string: '{vstr}'")

    def __str__(self) -> str:
        if self.minor is None:
            return f"{self.major}"
        else:
            return f"{self.major}.{self.minor}"


@define(auto_attribs=True, frozen=True)
class NestedField:
    name: str
    type: Type
    comment: str = field(converter=str.strip, repr=False)
    version: Version | None = field(converter=Version.from_opt_str)

    def __str__(self) -> str:
        if self.version:
            return "\n* ``{}`` :versionbadge:`clang-format {}`\n{}".format(
                self.name,
                self.version,
                doxygen2rst(indent(self.comment, 2, indent_first_line=False)),
            )
        return "\n* ``{}`` {}".format(
            self.name,
            doxygen2rst(indent(self.comment, 2, indent_first_line=False)),
        )


@define(auto_attribs=True, frozen=True)
class EnumValue:
    name: str
    comment: str = field(repr=False)
    config: str

    def __str__(self) -> str:
        return "* ``{}`` (in configuration: ``{}``)\n{}".format(
            self.name,
            re.sub(".*_", "", self.config),
            doxygen2rst(indent(self.comment, 2)),
        )


@define(auto_attribs=True, frozen=True)
class Enum:
    name: str
    type: Type
    comment: str = field(converter=str.strip, repr=False)
    values: list[EnumValue] = Factory(list)

    def __str__(self) -> str:
        return "\n".join(map(str, self.values))


@define(auto_attribs=True, frozen=True)
class NestedEnum:
    name: str
    type: Type
    comment: str = field(repr=False)
    version: Version | None = field(converter=Version.from_opt_str)
    values: list
    args: argparse.Namespace = field(repr=False)

    def __str__(self) -> str:
        s = ""
        if self.version:
            s = "\n* ``{} {}`` :versionbadge:`clang-format {}`\n\n{}".format(
                self.type.yaml_name,
                self.name,
                self.version,
                doxygen2rst(indent(self.comment, 2)),
            )
        else:
            s = "\n* ``{} {}``\n{}".format(
                self.type.yaml_name,
                self.name,
                doxygen2rst(indent(self.comment, 2)),
            )
        s += indent("\nPossible values:\n\n", 2)
        s += indent("\n".join(map(str, self.values)), 2)
        return s


@define(auto_attribs=True, frozen=True)
class NestedStruct:
    name: str
    type: Type
    comment: str = field(converter=str.strip, repr=False)
    values: list[NestedEnum | NestedField] = Factory(list)

    def __str__(self) -> str:
        return self.comment + "\n" + "\n".join(map(str, self.values))


@define(auto_attribs=True)
class Option:
    name: str
    type: Type
    comment: str = field(converter=str.strip, repr=False)
    version: Version | None = field(converter=Version.from_opt_str)
    args: argparse.Namespace = field(repr=False)
    enum: Enum | None = field(init=False, default=None)
    nested_struct: NestedStruct | None = field(init=False, default=None)

    def __str__(self) -> str:
        s = f".. _{self.name}:\n\n**{self.name}** (``{self.type.yaml_name}``) "
        if self.version:
            s += f":versionbadge:`clang-format {self.version}` "
        s += f":ref:`¶ <{self.name}>`\n{doxygen2rst(indent(self.comment, 2))}"
        if self.enum and self.enum.values:
            s += indent(f"\n\nPossible values:\n\n{self.enum}\n", 2)
        if self.nested_struct:
            s += indent(f"\n\nNested configuration flags:\n\n{self.nested_struct}\n", 2)
            s = s.replace("<option-name>", self.name)
        return s


def enum_cxx_type_name_is_deprecated(name: str) -> bool:
    return name in (
        "DefinitionReturnTypeBreakingStyle",
        "ReturnTypeBreakingStyle",
        "SpaceBeforeParensStyle",
    )


@define(auto_attribs=True)
class OptionsReader:
    header: TextIOWrapper
    args: argparse.Namespace = field(repr=False)
    in_code_block: bool = field(init=False, default=False)
    code_indent: int = field(init=False, default=0)
    lineno: int = field(init=False, default=0)
    last_err_lineno: int = field(init=False, default=-1)

    def __file_path(self) -> str:
        return os.path.relpath(self.header.name, str(self.args.clang_dir))

    def __print_line(self, line: str) -> None:
        print(f"{self.lineno:>6} | {line}", file=sys.stderr)

    def __warning(self, msg: str, line: str) -> None:
        print(f"{self.__file_path()}:{self.lineno}: warning: {msg}:", file=sys.stderr)
        self.__print_line(line)

    def __clean_comment_line(self, line: str) -> str:
        match = re.match(r"^/// (?P<indent> +)?\\code(\{.(?P<lang>\w+)\})?$", line)
        if match:
            if self.in_code_block:
                self.__warning("`\\code` in another `\\code`", line)
            self.in_code_block = True
            indent_str = match.group("indent")
            if not indent_str:
                indent_str = ""
            self.code_indent = len(indent_str)
            lang = match.group("lang")
            if not lang:
                lang = "c++"
            return f"\n{indent_str}.. code-block:: {lang}\n\n"

        endcode_match = re.match(r"^/// +\\endcode$", line)
        if endcode_match:
            if not self.in_code_block:
                self.__warning("no correct `\\code` found before this `\\endcode`", line)
            self.in_code_block = False
            return ""

        # check code block indentation
        if (
            self.in_code_block
            and not line == "///"
            and not line.startswith("///  " + " " * self.code_indent)
        ):
            if self.last_err_lineno == self.lineno - 1:
                self.__print_line(line)
            else:
                self.__warning("code block should be indented", line)
            self.last_err_lineno = self.lineno

        match = re.match(r"^/// \\warning$", line)
        if match:
            return "\n.. warning::\n\n"

        endwarning_match = re.match(r"^/// +\\endwarning$", line)
        if endwarning_match:
            return ""

        match = re.match(r"^/// \\note$", line)
        if match:
            return "\n.. note::\n\n"

        endnote_match = re.match(r"^/// +\\endnote$", line)
        if endnote_match:
            return ""
        return line[4:] + "\n"

    def read_options(self) -> list[Option]:
        class State:
            (
                BeforeStruct,
                Finished,
                InStruct,
                InNestedStruct,
                InNestedFieldComment,
                InFieldComment,
                InEnum,
                InEnumMemberComment,
                InNestedEnum,
                InNestedEnumMemberComment,
            ) = range(10)

        state = State.BeforeStruct

        options: list[Option] = []
        enums: dict[Type, Enum] = {}
        nested_structs: dict[Type, NestedStruct] = {}
        comment: str = ""
        enum: Enum | None = None
        nested_struct: NestedStruct | None = None
        version: str | None = None
        field_type_str: str = "UNINIT_FIELD"
        field_type: Type | None = None

        BuiltinBool = Type.from_cxx("bool", self.args)
        BuiltinUnsigned = Type.from_cxx("unsigned", self.args)
        BuiltinInt = Type.from_cxx("int", self.args)
        BuiltinString = Type.from_cxx("std::string", self.args)
        BuiltinStringList = Type.from_cxx("std::vector<std::string>", self.args)
        BuiltinIncludeCategoryList = Type.from_cxx("std::vector<IncludeCategory>", self.args)
        BuiltinRawStringFormatList = Type.from_cxx("std::vector<RawStringFormat>", self.args)
        BuiltinOptionalUnsigned = Type.from_cxx("std::optional<unsigned>", self.args)
        BuiltinDeprecated = Type.from_cxx("deprecated", self.args, is_deprecated=True)

        builtin_types: list[Type] = [
            BuiltinBool,
            BuiltinUnsigned,
            BuiltinInt,
            BuiltinString,
            BuiltinStringList,
            BuiltinIncludeCategoryList,
            BuiltinRawStringFormatList,
            BuiltinOptionalUnsigned,
            BuiltinDeprecated,
        ]

        for line in self.header:
            self.lineno += 1
            line = line.strip()
            if state == State.BeforeStruct:
                if line in ("struct FormatStyle {", "struct IncludeStyle {"):
                    state = State.InStruct
            elif state == State.InStruct:
                if line.startswith("///"):
                    state = State.InFieldComment
                    comment = self.__clean_comment_line(line)
                elif line == "};":
                    state = State.Finished
                    break
            elif state == State.InFieldComment:
                if line.startswith(r"/// \version"):
                    match = re.match(r"/// \\version\s*(?P<version>[0-9.]+)*", line)
                    if match:
                        version = match.group("version")
                elif line.startswith("///"):
                    comment += self.__clean_comment_line(line)
                elif line.startswith("enum"):
                    state = State.InEnum
                    name = re.sub(r"enum\s+(\w+)\s*(:((\s*\w+)+)\s*)?\{", "\\1", line)
                    field_type = Type.from_cxx(
                        name, self.args, enum_cxx_type_name_is_deprecated(name)
                    )
                    enum = Enum(name, field_type, comment)
                    field_type = None
                elif line.startswith("struct"):
                    state = State.InNestedStruct
                    name = re.sub(r"struct\s+(\w+)\s*\{", "\\1", line)
                    nested_struct = NestedStruct(name, Type.from_cxx(name, self.args), comment)
                elif line.endswith(";"):
                    prefix = "// "
                    if line.startswith(prefix):
                        line = line[len(prefix) :]
                    state = State.InStruct
                    match = re.match(r"([<>:\w(,\s)]+)\s+(\w+);", line)
                    if match is None:
                        raise ValueError(f"bad RE on '{line}'")
                    field_type_str, field_name = match.groups()
                    field_type = Type.from_cxx(
                        field_type_str, self.args, enum_cxx_type_name_is_deprecated(field_type_str)
                    )
                    if not version:
                        self.__warning(f"missing version for {field_name}", line)
                    option = Option(
                        field_name,
                        field_type,
                        comment,
                        version,
                        self.args,
                    )
                    options.append(option)
                    version = None
                    field_type = None
                else:
                    raise ValueError("Invalid format, expected comment, field or enum\n" + line)
            elif state == State.InNestedStruct:
                if line.startswith("///"):
                    state = State.InNestedFieldComment
                    comment = self.__clean_comment_line(line)
                elif line == "};":
                    state = State.InStruct
                    if nested_struct is None:
                        raise ValueError("nested_struct not initialized")
                    nested_structs[nested_struct.type] = nested_struct
            elif state == State.InNestedFieldComment:
                if line.startswith(r"/// \version"):
                    match = re.match(r"/// \\version\s*(?P<version>[0-9.]+)*", line)
                    if match:
                        version = match.group("version")
                elif line.startswith("///"):
                    comment += self.__clean_comment_line(line)
                elif line.startswith("enum"):
                    state = State.InNestedEnum
                    name = re.sub(r"enum\s+(\w+)\s*(:((\s*\w+)+)\s*)?\{", "\\1", line)
                    field_type = Type.from_cxx(
                        name, self.args, enum_cxx_type_name_is_deprecated(name)
                    )
                    if name == "ReturnTypeBreakingStyle":
                        print(f"ReturnTypeBreakingStyle: line: {line} field_type: {field_type}")
                    enum = Enum(name, field_type, comment)
                    field_type = None
                else:
                    state = State.InNestedStruct
                    match = re.match(r"([<>:\w(,\s)]+)\s+(\w+);", line)
                    if match is None:
                        raise ValueError(f"bad RE on '{line}'")
                    field_type_str, field_name = match.groups()
                    # if not version:
                    #     self.__warning(f"missing version for {field_type_str}", line)
                    if nested_struct is None:
                        raise ValueError("nested_struct not initialized")
                    field_type = Type.from_cxx(field_type_str, self.args)
                    if field_type in enums:
                        new_nested_enum = NestedEnum(
                            field_name,
                            field_type,
                            comment,
                            version,
                            enums[field_type].values,
                            self.args,
                        )
                        if new_nested_enum in nested_struct.values:
                            raise ValueError(
                                f"new_nested_enum in nested_struct.values: {new_nested_enum}"
                            )
                        nested_struct.values.append(new_nested_enum)
                    else:
                        new_nested_field = NestedField(field_name, field_type, comment, version)
                        if new_nested_field in nested_struct.values:
                            raise ValueError(
                                f"new_nested_field in nested_struct.values: {new_nested_field}"
                            )
                        nested_struct.values.append(new_nested_field)
                    version = None
                    field_type = None
            elif state == State.InEnum:
                if line.startswith("///"):
                    state = State.InEnumMemberComment
                    comment = self.__clean_comment_line(line)
                elif line == "};":
                    state = State.InStruct
                    if enum is None:
                        raise ValueError("enum not initialized")
                    enums[enum.type] = enum
                else:
                    # Enum member without documentation. Must be documented
                    # where the enum is used.
                    pass
            elif state == State.InNestedEnum:
                if line.startswith("///"):
                    state = State.InNestedEnumMemberComment
                    comment = self.__clean_comment_line(line)
                elif line == "};":
                    state = State.InNestedStruct
                    if enum is None:
                        raise ValueError("enum not initialized")
                    enums[enum.type] = enum
                else:
                    # Enum member without documentation. Must be
                    # documented where the enum is used.
                    pass
            elif state == State.InEnumMemberComment:
                if line.startswith("///"):
                    comment += self.__clean_comment_line(line)
                else:
                    state = State.InEnum
                    val = line.replace(",", "")
                    pos = val.find(" // ")
                    if pos != -1:
                        config = val[pos + 4 :]
                        val = val[:pos]
                    else:
                        config = val
                    if enum is None:
                        raise ValueError("enum not initialized")
                    enum.values.append(EnumValue(val, comment, config))
            elif state == State.InNestedEnumMemberComment:
                if line.startswith("///"):
                    comment += self.__clean_comment_line(line)
                else:
                    state = State.InNestedEnum
                    val = line.replace(",", "")
                    pos = val.find(" // ")
                    if pos != -1:
                        config = val[pos + 4 :]
                        val = val[:pos]
                    else:
                        config = val
                    if enum is None:
                        raise ValueError("enum not initialized")
                    enum.values.append(EnumValue(val, comment, config))
        if state != State.Finished:
            raise RuntimeError("Not finished by the end of file")

        for option in options:
            if option.type not in builtin_types:
                if option.type in enums:
                    option.enum = enums[option.type]
                elif option.type in nested_structs:
                    option.nested_struct = nested_structs[option.type]
                else:
                    raise ValueError(f"Unknown type: {option.type} option: {option}")
        return options


def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", help="path of output file")
    parser.add_argument("-c", "--clang-dir", type=Path, help="path of clang source root")
    return parser


def real_main(args: argparse.Namespace) -> None:
    with open(PLURALS_FILE(args)) as f:
        f.seek(0)
        global plurals
        plurals = set(f.read().splitlines())
    with open(FORMAT_STYLE_FILE(args)) as f:
        opts = OptionsReader(f, args).read_options()
    with open(INCLUDE_STYLE_FILE(args)) as f:
        opts += OptionsReader(f, args).read_options()

    opts = sorted(opts, key=lambda x: x.name)
    # rich.print(opts)
    print(opts)
    options_text = "\n\n".join(map(str, opts))

    with open(args.output, "w") as f:
        f.write(options_text)


def main() -> None:
    real_main(get_arg_parser().parse_args())


if __name__ == "__main__":
    main()
