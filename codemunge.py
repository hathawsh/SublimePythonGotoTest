
"""Use the ast module to parse class and function declarations."""

import ast
import re
import weakref

empty_line_re = re.compile(r'\s*$')


class Decl(object):
    """A function or class declaration statement."""
    def __init__(self, name, first_row, last_row=None, children=None):
        self.name = name
        self.first_row = first_row
        # Note: last_row includes the blank rows after the declaration.
        self.last_row = last_row
        self.children = children or []
        self.parent_ref = None  # A weakref.ref

    def get_path(self):
        path = []
        decl = self
        while decl is not None:
            path.append(decl)
            parent = decl.parent_ref()
            if parent is None or isinstance(parent, ModuleDecl):
                break
            decl = parent
        path.reverse()
        return path

    def __repr__(self):
        return ('{0}({1!r}, {2!r}, {3!r}, {4!r})'
                .format(self.__class__.__name__,
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


class Visitor(ast.NodeVisitor):

    def __init__(self, lines):
        self.parent = self.top = ModuleDecl('', 0)
        self.lines = lines
        self.last_lineno = 1
        self.closing_decls = []

    def visitdecl(self, node, cls):
        decl = cls(node.name, node.lineno - 1)
        parent = self.parent
        decl.parent_ref = weakref.ref(parent)
        parent.children.append(decl)
        self.last_lineno = node.lineno
        self.parent = decl
        self.generic_visit(node)
        self.parent = parent
        decl.last_row = self.last_lineno - 1
        self.closing_decls.append(decl)

    def visit_FunctionDef(self, node):
        self.close_decls(node.lineno)
        self.visitdecl(node, FuncDecl)

    def visit_ClassDef(self, node):
        self.close_decls(node.lineno)
        self.visitdecl(node, ClassDecl)

    def generic_visit(self, node):
        if hasattr(node, 'lineno'):
            self.close_decls(node.lineno)
            self.last_lineno = max(self.last_lineno, node.lineno)
        super(Visitor, self).generic_visit(node)

    def close_decls(self, new_lineno):
        decls = self.closing_decls
        if decls:
            # Change the range of the closing declarations to include
            # multi-line expressions, but not blank lines.
            # To compute last_row, subtract 1 because the previous
            # declaration ends on the line before;
            # subtract 1 again because rows are zero-based while lines are
            # one-based.
            last_row = new_lineno - 2
            while last_row > 0 and last_row < len(self.lines):
                line = self.lines[last_row]
                if not line or empty_line_re.match(line):
                    # Ignore an empty line.
                    last_row -= 1
                else:
                    break
            for decl in decls:
                decl.last_row = max(last_row, decl.last_row)
            del self.closing_decls[:]


def list_decls(content, filename):
    """List the nested declarations in a module."""
    node = ast.parse(content, filename)
    lines = content.splitlines()
    visitor = Visitor(lines)
    visitor.visit(node)
    if visitor.closing_decls:
        visitor.close_decls(len(lines) + 1)
    return visitor.top.children


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
    content = ("if 1:\n"          # row 0
               " def foo():\n"    # row 1
               "  pass\n"         # row 2
               "\n"               # row 3
               "\n"               # row 4
               " class bar():\n"  # row 5
               "  def baz():\n"   # row 6
               "   def zed():\n"  # row 7
               "    return [\n"   # row 8
               "     1]\n"        # row 9
               "\n"               # row 10
               " # hi!\n"         # row 11
               "  stop = True\n"  # row 12
               "class Y: pass\n"  # row 13
               "class Z:\n"       # row 14
               " '''stuff\n"      # row 15
               "... more '''\n"   # row 16
               "\n")              # row 17
    decls = list_decls(content, 'codemunge_test')
    import pprint
    pprint.pprint(decls)
    assert len(decls) == 4

    assert decls[0].name == 'foo'
    assert len(decls[0].children) == 0
    assert decls[0].first_row == 1
    assert decls[0].last_row == 2

    assert decls[1].name == 'bar'
    assert len(decls[1].children) == 1
    assert decls[1].first_row == 5
    assert decls[1].last_row == 12
    assert decls[1].children[0].name == 'baz'
    assert decls[1].children[0].first_row == 6
    assert decls[1].children[0].last_row == 11
    assert len(decls[1].children[0].children) == 1
    assert decls[1].children[0].children[0].name == 'zed'
    assert decls[1].children[0].children[0].first_row == 7
    assert decls[1].children[0].children[0].last_row == 11

    assert decls[2].name == 'Y'
    assert len(decls[2].children) == 0
    assert decls[2].first_row == 13
    assert decls[2].last_row == 13

    assert decls[3].name == 'Z'
    assert len(decls[3].children) == 0
    assert decls[3].first_row == 14
    assert decls[3].last_row == 16


if __name__ == '__main__':
    test_list_decls()
