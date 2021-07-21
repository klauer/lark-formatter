lark-formatter
==============

Simple attempt at a lark-parser grammar formatter, using Lark to lex the
grammar.


Installation
------------

Requires:
* Python 3.7+
* lark-parser

```bash
$ pip install .
```

Usage
-----

```bash
$ lark-formatter input_grammar.lark
$ cat input_grammar.lark | lark-formatter
```

Or in vim, to format part of a buffer, make a visual selection and then:

```
:!lark-format
```
(vim will automatically insert ``:'<,'>`` at the front, indicating the visual
selection region)

Notes
-----

* Likely will not work on everything
* No guarantees it won't mess up your grammar. Make sure it's
  version-controlled first!
* ``->`` aliases are not aligned
* Spacing between comments and sections could use work
* ``check`` tool probably isn't good enough yet
