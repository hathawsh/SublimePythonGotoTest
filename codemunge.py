
"""Use the ast module to parse class and function declarations."""

import ast
import weakref


class Decl(object):
    """A function or class declaration statement."""
    def __init__(self, name, first_row, last_row=None, children=None):
        self.name = name
        self.first_row = first_row
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

    def __init__(self):
        self.parent = self.top = ModuleDecl('', 0)
        self.last_lineno = 1

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

    def visit_FunctionDef(self, node):
        self.visitdecl(node, FuncDecl)

    def visit_ClassDef(self, node):
        self.visitdecl(node, ClassDecl)

    def generic_visit(self, node):
        if hasattr(node, 'lineno'):
            self.last_lineno = max(self.last_lineno, node.lineno)
        super(Visitor, self).generic_visit(node)


def list_decls(content, filename):
    """List the nested declarations in a module."""
    node = ast.parse(content, filename)
    visitor = Visitor()
    visitor.visit(node)
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
    content = ("if 1:\n"
               " def foo():\n"
               "  pass\n"
               "\n"
               " class bar():\n"
               "  def baz():\n"
               "   return 1\n"
               "\n"
               " # hi!\n"
               "  stop = True\n"
               "class Y: pass\n"
               "class Z:\n"
               " pass")
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
    assert decls[1].first_row == 4
    assert decls[1].last_row == 9
    assert decls[1].children[0].name == 'baz'
    assert decls[1].children[0].first_row == 5
    assert decls[1].children[0].last_row == 6

    assert decls[2].name == 'Y'
    assert len(decls[2].children) == 0
    assert decls[2].first_row == 10
    assert decls[2].last_row == 10

    assert decls[3].name == 'Z'
    assert len(decls[3].children) == 0
    assert decls[3].first_row == 11
    assert decls[3].last_row == 12


if __name__ == '__main__':
    test_list_decls()
