
import re
import weakref


decl_re = re.compile(r'(\s*)(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)')
other_code_re = re.compile(r'(\s*)(#)?\S+')
tab_replacement = ' ' * 8


class Decl(object):

    def __init__(self, indent, name, first_row, last_row=None, children=None):
        self.indent = indent
        self.name = name
        self.first_row = first_row
        self.last_row = last_row
        self.children = children or []
        self.parent_ref = None  # A weakref.ref

    def __repr__(self):
        return ('{}({!r}, {!r}, {!r}, {!r}, {!r})'
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
    top = ModuleDecl(-1, '', 0)
    prev = top

    for row, line in enumerate(content.split('\n')):
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

    close_decls(prev, 0, row + 1)
    return top.children


def close_decls(decl, indent, row):
    """Given a new indentation level, close declarations and return the parent.
    """
    while indent <= decl.indent:
        decl.last_row = row - 1
        decl = decl.parent_ref()
    return decl


def test_list_decls():
    content = ("if 1:\n"
               " def foo():\n"
               "  pass\n"
               " class bar():\n"
               "  def baz():\n"
               "   pass\n"
               "  stop = True\n"
               "class Y: pass\n"
               "class Z:\n"
               " pass")
    decls = list_decls(content)
    assert len(decls) == 4
    assert decls[0].name == 'foo'
    assert len(decls[0].children) == 0
    assert decls[1].name == 'bar'
    assert len(decls[1].children) == 1
    assert decls[1].children[0].name == 'baz'
    assert decls[2].name == 'Y'
    assert decls[3].name == 'Z'
    print decls


if __name__ == '__main__':
    test_list_decls()
