"""
Simple tool to reformat Lark grammars.
"""

import argparse
import collections
import dataclasses
import io
import logging
import os
import sys
from typing import Deque, List, Optional, Tuple, Type, Union

import lark

logger = logging.getLogger(__name__)
DESCRIPTION = __doc__


@dataclasses.dataclass
class ReformatterState:
    grammar: str
    in_rule: Optional[str] = None
    rule_indent: int = 0
    parentheses: int = 0
    square_brackets: int = 0
    curly_braces: int = 0
    comments: List[str] = dataclasses.field(default_factory=list)
    tokens: Deque[lark.Token] = dataclasses.field(default_factory=collections.deque)
    buffer: io.StringIO = dataclasses.field(default_factory=io.StringIO)


class ReformatterContext:
    lark_grammar: lark.Lark
    tokens: Optional[List[lark.Token]]
    buffer: io.StringIO

    def __init__(self, lark_grammar: lark.Lark, input_grammar: str):
        self.lark_grammar = lark_grammar
        self.state = ReformatterState(grammar=input_grammar)
        self.state.tokens = collections.deque(
            lark_grammar.lex(input_grammar, dont_ignore=True)
        )
        self.buffer = self.state.buffer
        self.special_handlers = {
            "->": self.handle_arrow,
            "..": self.handle_range,
            "%import": self.handle_import,
            "%ignore": self.handle_ignore,
            "%override": self.handle_override,
            "%declare": self.handle_declare,
        }

    def reformat(self) -> str:
        """Reformat the provided grammar."""
        while self.state.tokens:
            token = self.state.tokens.popleft()
            if token.type in {"WS_INLINE", }:
                continue
            handler_name = f"handle_{token.type}"
            handler = getattr(
                self, handler_name,
                self.special_handlers.get(token, None)
            )

            if handler is not None:
                handler(token)
            else:
                raise RuntimeError(
                    f"TODO unhandled {token!r} {token.type} "
                    f"on line {token.line} column {token.column}"
                )

        lines = (
            line.rstrip()
            for line in self.state.buffer.getvalue().splitlines()
        )
        return "\n".join(lines).strip()

    def eat_subsequent(self, *token_types):
        """Eat all upcoming tokens matching ``token_types`` (or whitespace)."""
        token_types = set(token_types)
        token_types.add("WS_INLINE")
        while self.next_token_type in token_types:
            self.state.tokens.popleft()

    @property
    def next_token(self):
        """The next token to be evaluated."""
        if self.state.tokens:
            return self.state.tokens[0]

    @property
    def next_token_type(self):
        """The next token to be evaluated."""
        if self.state.tokens:
            return self.next_token.type

    @property
    def next_actual_token(self) -> Optional[lark.Token]:
        """The next token to be evaluated, excluding whitespace."""
        for tok in self.state.tokens:
            if tok and tok.type not in ("WS_INLINE", ):
                return tok

    @property
    def next_actual_token_type(self) -> Optional[str]:
        """The next token to be evaluated, excluding whitespace."""
        return getattr(self.next_actual_token, "type", None)

    def eat_until(self, token_types=None, token_values=None, ignore=None):
        """Eat tokens until a matching type or value."""
        token_types = set(token_types or [])
        ignore = set(ignore or [])
        token_values = set(token_values or [])

        def should_continue():
            return (
                self.state.tokens and
                self.next_token_type not in token_types and
                self.next_token not in token_values
            )

        while should_continue():
            tok = self.state.tokens.popleft()
            if tok.type not in ignore:
                yield tok

    def get_last_char(self) -> Optional[str]:
        """The last character in the output."""
        return (self.buffer.getvalue() or [None])[-1]

    @property
    def should_add_space(self):
        """Should the next item add a space?"""
        return self.get_last_char() not in " \t"

    def append(self, text: str, add_space_if_needed: bool = True):
        """Append text to the buffer."""
        if add_space_if_needed and self.should_add_space:
            print(" ", end="", file=self.buffer)
        print(text, end="", file=self.buffer)

    def right_strip_output(self):
        # Well now that's inefficient
        self.buffer.seek(len(self.buffer.getvalue().rstrip()))

    def get_last_line(self):
        # Well now that's very inefficient
        buf = self.buffer.getvalue()
        return buf.splitlines()[-1] if buf else ""

    def ensure_newline(self):
        """Ensure we're on a new line."""
        buf = self.buffer.getvalue()
        if not buf:
            return

        if buf[-1] != "\n":
            print(file=self.buffer)

    @property
    def previous_line_is_comment(self) -> bool:
        return self.get_last_line().startswith("//")

    def output_comments(self) -> bool:
        if not self.state.comments:
            return False

        self.ensure_newline()
        if not self.previous_line_is_comment:
            print(file=self.buffer)

        for comment in list(self.state.comments):
            print(comment.strip(), file=self.buffer)

        self.state.comments.clear()
        return True

    def newline(self, with_comments=True):
        if with_comments and self.output_comments():
            return
        print(file=self.buffer)

    def handle_RULE(self, token: lark.Token):
        self.output_comments()

        if self.state.in_rule:
            print(f"{token} ", end="", file=self.buffer)
        elif self.next_actual_token in {":", ".", "{"}:
            if not self.previous_line_is_comment:
                self.newline()
            priority = "".join(self.eat_until(token_types={"COLON"}))
            header = f"{token}{priority}".replace(" ", "")
            print(f"{header}: ", end="", file=self.buffer)
            self.state.rule_indent = len(header)
            self.eat_subsequent("COLON")
            self.state.in_rule = token
        else:
            raise RuntimeError(
                f"Not in a rule, and next token doesn't look like the start "
                f"of a rule: {self.next_actual_token}"
            )

    def handle_TOKEN(self, token: lark.Token):
        self.output_comments()
        if self.next_actual_token in {":", "."}:
            if self.state.in_rule:
                self.newline()
            self.state.in_rule = token
            priority = "".join(self.eat_until(token_types={"COLON"}))
            header = f"{token}{priority}".replace(" ", "")
            self.state.rule_indent = len(header)
            print(f"{header}: ", end="", file=self.buffer)
            self.eat_subsequent("COLON")
        else:
            print(f"{token}", end=" ", file=self.buffer)

    def handle_NUMBER(self, token: lark.Token):
        print(f" {token} ", end="", file=self.buffer)

    def handle_LPAR(self, token: lark.Token):
        self.state.parentheses += 1
        self.append("( ")

    def handle_RPAR(self, token: lark.Token):
        self.state.parentheses -= 1
        self.append(") ")

    def handle_LBRACE(self, token: lark.Token):
        self.state.curly_braces += 1
        self.append("{ ", add_space_if_needed=False)

    def handle_RBRACE(self, token: lark.Token):
        self.state.curly_braces -= 1
        self.append("} ", add_space_if_needed=False)

    def handle_LSQB(self, token: lark.Token):
        self.state.square_brackets += 1
        self.append("[ ")

    def handle_RSQB(self, token: lark.Token):
        self.state.square_brackets -= 1
        self.append("] ")

    def handle_OP(self, token: lark.Token):
        """Operator."""
        if token in {"*", "?"}:
            self.right_strip_output()
        print(str(token), end=" ", file=self.buffer)

    def handle__NL(self, _: lark.Token):
        """Newline."""
        if self.state.in_rule:
            self.newline()
        self.state.in_rule = None
        self.eat_subsequent("_NL")

    def handle_STRING(self, token: lark.Token):
        print(token, end=" ", file=self.buffer)

    def handle_COLON(self, token: lark.Token):
        print(token, end=" ", file=self.buffer)

    def handle_REGEXP(self, token: lark.Token):
        print(token, end=" ", file=self.buffer)

    def handle_DOT(self, token: lark.Token):
        print(token, end=" ", file=self.buffer)

    def handle_range(self, token: lark.Token):
        self.right_strip_output()
        print("..", end="", file=self.buffer)

    def handle_arrow(self, token: lark.Token):
        print(f" {token} ", end="", file=self.buffer)

    def handle_import(self, _: lark.Token):
        import_name = "".join(
            tok
            for tok in self.eat_until({"_NL", "LPAR"}, {"->"}, ignore={"WS_INLINE", })
        )
        print("", file=self.buffer)
        print(f"%import {import_name}", end="", file=self.buffer)
        if self.next_token_type == "_NL":
            self.eat_subsequent("_NL")
            self.newline()
            if self.next_actual_token != "%import":
                self.newline()

    def handle_ignore(self, _: lark.Token):
        expansions = " ".join(
            tok
            for tok in self.eat_until({"_NL"}, ignore={"WS_INLINE", })
        )
        print("", file=self.buffer)
        print(f"%ignore {expansions}", end="", file=self.buffer)
        self.eat_subsequent("_NL")
        if self.next_actual_token != "%ignore":
            self.newline()

    def handle_override(self, _: lark.Token):
        rule = " ".join(
            tok
            for tok in self.eat_until({"_NL"}, ignore={"WS_INLINE", })
        )
        print("", file=self.buffer)
        print(f"%override {rule}", end="", file=self.buffer)
        self.eat_subsequent("_NL")
        if self.next_actual_token != "%override":
            self.newline()

    def handle_declare(self, _: lark.Token):
        names = " ".join(
            tok
            for tok in self.eat_until({"_NL"}, ignore={"WS_INLINE", })
        )
        print("", file=self.buffer)
        print(f"%declare {names}", end="", file=self.buffer)
        self.eat_subsequent("_NL")
        if self.next_actual_token != "%declare":
            self.newline()

    def handle__VBAR(self, _: lark.Token):
        if self.state.in_rule and self.state.parentheses == 0 and self.state.square_brackets == 0:
            print(file=self.buffer)
            print(" " * self.state.rule_indent + "| ",
                  end="", file=self.buffer)
        else:
            self.right_strip_output()
            print(" | ", end="", file=self.buffer)

    def handle_COMMENT(self, token: lark.Token):
        self.state.comments.append(token)


class FormatHelper:
    lark_grammar: lark.Lark
    context_class: Type[ReformatterContext] = ReformatterContext

    def __init__(self):
        self.lark_grammar = lark.Lark.open_from_package(
            "lark", "lark.lark", search_paths=("grammars", ),
            parser="lalr",
            maybe_placeholders=True,
            propagate_positions=True,
        )

    def reformat(
        self,
        grammar: Union[lark.Lark, str],
        check: bool = True
    ) -> Tuple[ReformatterContext, str]:
        """Reformat the given lark grammar."""
        if isinstance(grammar, lark.Lark):
            grammar = grammar.source_grammar
        else:
            # Make sure it's valid, at least
            self.lark_grammar.parse(grammar)

        ctx: ReformatterContext = self.context_class(
            lark_grammar=self.lark_grammar,
            input_grammar=grammar,
        )
        reformatted = ctx.reformat()
        if check:
            self.compare(grammar, reformatted)

        return ctx, reformatted

    def compare(self, original: str, new: str) -> bool:
        """Compare grammar tokens, ignoring whitespace and comments."""
        source_tokens = self.lark_grammar.lex(original, dont_ignore=False)
        result_tokens = self.lark_grammar.lex(new, dont_ignore=False)
        result = True
        # assert core_source_tokens == core_result_tokens
        for tok1, tok2 in zip(source_tokens, result_tokens):
            if tok1 != tok2 and tok1.strip() != tok2.strip():
                logger.warning("Token mismatch? source=%s formatted=%s", tok1, tok2)
                result = False
        return result


def reformat(grammar, check=True) -> str:
    """Reformat the provided lark grammar."""
    reformatter = FormatHelper()
    ctx, reformatted = reformatter.reformat(grammar, check=check)
    return reformatted


def main():
    """Reformat the provided lark grammar."""
    parser = argparse.ArgumentParser(
        prog="lark-format",
        description=DESCRIPTION,
    )
    parser.add_argument(
        "filename",
        type=argparse.FileType("rt"),
        nargs="?" if not os.isatty(0) else None,
        default=sys.stdin,
        help="The .lark grammar filename (or '-' for stdin)"
    )
    parser.add_argument(
        "--no-check", dest="check", action="store_false",
        help="Do not comparing the output grammar with the input"
    )
    args = parser.parse_args()
    grammar = args.filename.read()

    print(reformat(grammar, check=args.check))


if __name__ == "__main__":
    main()
