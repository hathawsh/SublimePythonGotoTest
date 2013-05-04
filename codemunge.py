
import re
import weakref


decl_re = re.compile(r'(\s*)(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)')
other_code_re = re.compile(r'(\s*)(#)?\S')
tab_replacement = ' ' * 8


class Decl(object):
    """A declaration statement. Usually starts with 'def' or 'class'.
    """
    def __init__(self, indent, name, first_row, last_row=None, children=None):
        self.indent = indent
        self.name = name
        self.first_row = first_row
        self.last_row = last_row
        self.children = children or []
        self.parent_ref = None  # A weakref.ref

    def __repr__(self):
        return ('{0}({1!r}, {2!r}, {3!r}, {4!r}, {5!r})'
                .format(self.__class__.__name__,
                        self.indent,
                        self.name,
                        self.first_row,
                        self.last_row,
                        self.children))


class ModuleDecl(Decl):
    pass


class ClassDecl(Decl):
    pass


class FuncDecl(Decl):
    pass


decl_types = {'class': ClassDecl,
              'def': FuncDecl}


def measure_indent(indent_chars):
    return len(indent_chars.replace('\t', tab_replacement))


def list_decls(content):
    """List the nested declarations in a module."""
    top = ModuleDecl(-1, '', 0)
    prev = top

    lines = content.split('\n')
    for row, line in enumerate(lines):
        match = decl_re.match(line)
        if match is not None:
            indent_chars, decl_type, name = match.groups()
            indent = measure_indent(indent_chars)
            decl = decl_types[decl_type](indent, name, row)
            parent = close_decls(prev, indent, row)
            decl.parent_ref = weakref.ref(parent)
            parent.children.append(decl)
            prev = decl

        else:
            m = other_code_re.match(line)
            if m is not None:
                indent_chars, comment = m.groups()
                if not comment:
                    indent = measure_indent(indent_chars)
                    prev = close_decls(prev, indent, row)

    close_decls(prev, 0, len(lines))
    return top.children


def close_decls(decl, indent, row):
    """Given a new indentation level, close declarations and return the parent.
    """
    while indent <= decl.indent:
        decl.last_row = row - 1
        decl = decl.parent_ref()
    return decl


def find_decl_for_row(decls, row):
    for decl in decls:
        if row >= decl.first_row and row <= decl.last_row:
            child = find_decl_for_row(decl.children, row)
            if child is not None:
                return child
            else:
                return decl
    return None


def test_list_decls():
    content = ("if 1:\n"
               " def foo():\n"
               "  pass\n"
               " class bar():\n"
               "  def baz():\n"
               "   pass\n"
               " # hi!\n"
               "  stop = True\n"
               "class Y: pass\n"
               "class Z:\n"
               " pass")
    decls = list_decls(content)
    assert len(decls) == 4
    assert decls[0].name == 'foo'
    assert len(decls[0].children) == 0
    assert decls[0].first_row == 1
    assert decls[0].last_row == 2

    assert decls[1].name == 'bar'
    assert len(decls[1].children) == 1
    assert decls[1].first_row == 3
    assert decls[1].last_row == 5
    assert decls[1].children[0].name == 'baz'
    assert decls[1].children[0].first_row == 4
    assert decls[1].children[0].last_row == 5

    assert decls[2].name == 'Y'
    assert len(decls[2].children) == 0
    assert decls[2].first_row == 8
    assert decls[2].last_row == 8

    assert decls[3].name == 'Z'
    assert len(decls[3].children) == 0
    assert decls[3].first_row == 9
    assert decls[3].last_row == 10


if __name__ == '__main__':
    test_list_decls()
