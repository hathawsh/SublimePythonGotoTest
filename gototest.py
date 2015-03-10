
import ast
import os
import re
import sublime
import sublime_plugin
import weakref


try:
    # Python 2
    execfile

except NameError:

    # Python 3
    exe = eval('exec')  # Shield from Python 2 syntax errors

    def execfile(fn, global_vars, local_vars):
        with open(fn) as f:
            code = compile(f.read(), fn, 'exec')
            exe(code, global_vars, local_vars)


empty_line_re = re.compile(r'\s*$')
_deferred = {}  # {filename: CodeNavigator}
here = os.path.abspath(os.path.dirname(__file__))


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
    """Create a Decl tree from a Python abstract syntax tree."""

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
            # To compute last_row, subtract 1 from new_lineono because
            # the previous declaration ends on the line before;
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


class GotoTestCommand(sublime_plugin.TextCommand):
    """Go to the unit test for this Python code or vice-versa"""

    generate = False

    def run(self, edit):
        view = self.view
        fname = view.file_name()
        if not fname:
            sublime.status_message("SublimePythonGotoTest: "
                                   "No file name given.")
            return

        dirname, basename = os.path.split(fname)
        name, ext = os.path.splitext(basename)
        if ext != '.py':
            sublime.status_message("SublimePythonGotoTest: "
                                   "for .py files only.")
            return

        content = view.substr(sublime.Region(0, view.size()))
        point = view.sel()[0].begin()
        row, _col = view.rowcol(point)

        if os.path.basename(dirname) == 'tests':
            if basename.startswith('test_'):
                # The file is test code. Go to the main code.
                parent = os.path.dirname(dirname)
                main_name = basename[5:]
                if main_name == os.path.basename(parent) + '.py':
                    if not os.path.exists(os.path.join(parent, main_name)):
                        # This is a test of the package's __init__.py.
                        main_name = '__init__.py'
                target = os.path.join(parent, main_name)
                try:
                    nav = MainCodeNavigator(target_filename=target,
                                            source_filename=fname,
                                            content=content,
                                            source_row=row)
                except SyntaxError as e:
                    show_syntax_error(e)
                    return
            else:
                sublime.status_message("SublimePythonGotoTest: "
                                       "{0} is not a test module."
                                       .format(fname))
                return
        else:
            # The file is the main code. Go to the test code.
            parent = os.path.join(dirname, 'tests')
            main_name = basename
            if main_name == '__init__.py':
                package_name = os.path.basename(dirname)
                if not os.path.exists(os.path.join(dirname,
                                      package_name + '.py')):
                    # Make a test of the package's __init__.py.
                    main_name = package_name + '.py'
            test_fn = 'test_' + main_name
            target = os.path.join(parent, test_fn)

            try:
                nav = TestCodeNavigator(target_filename=target,
                                        source_filename=fname,
                                        content=content,
                                        source_row=row,
                                        generate=self.generate)
            except SyntaxError as e:
                show_syntax_error(e)
                return

            if not os.path.exists(parent):
                os.mkdir(parent)

            init_py = os.path.join(parent, '__init__.py')
            if not os.path.exists(init_py):
                # Create an empty __init__.py in the tests subdir.
                f = open(init_py, 'w')
                f.close()

        win = view.window()
        view = win.open_file(target)

        if view.is_loading():
            _deferred[os.path.abspath(target)] = nav
        else:
            nav.goto(view)


class GenerateTestCommand(GotoTestCommand):
    """Generate a stub unit test for this Python code"""
    generate = True


class Listener(sublime_plugin.EventListener):
    """Finish test generation right after a test module has been opened."""
    def on_load(self, view):
        fn = os.path.abspath(view.file_name())
        nav = _deferred.get(fn)
        if nav is not None:
            del _deferred[fn]
            nav.goto(view)


def show_syntax_error(e):
    sublime.error_message("SyntaxError: {0}".format(e))


def list_view_decls(view):
    content = view.substr(sublime.Region(0, view.size()))
    return list_decls(content, view.file_name())


def to_main_name(name):
    if name.startswith('Test_'):
        return name[5:]
    elif name.startswith('Test'):
        return name[4:]
    else:
        return None


def show_rows(view, first_row, last_row):
    """Position the cursor within a range of rows in a view."""
    first_point = view.text_point(first_row, 0)
    # last_point = view.text_point(last_row + 1, 0)
    view.sel().clear()
    view.sel().add(sublime.Region(first_point))
    view.show(first_point)


class InsertAtCommand(sublime_plugin.TextCommand):
    """Like the insert command, but insert at a specific point."""
    def run(self, edit, point, string):
        view = self.view
        view.insert(edit, point, string)


def insert_rows(view, row, content, margin=2):
    point = view.text_point(row, 0)

    if margin:
        if row > 0:
            # Add blank lines before.
            region = sublime.Region(max(0, point - margin - 1), point)
            text_before = view.substr(region)
            blanks = 0
            for c in reversed(text_before):
                if c == '\n':
                    blanks += 1
                else:
                    break
            if blanks < margin + 1:
                content = '\n' * (margin + 1 - blanks) + content

        if point < view.size() - 1:
            # Add blank lines after.
            region = sublime.Region(point, min(view.size(), point + margin))
            text_after = view.substr(region)
            blanks = 0
            for c in text_after:
                if c == '\n':
                    blanks += 1
                else:
                    break
            if blanks < margin:
                content = content + '\n' * (margin - blanks)

    view.run_command('insert_at', {'point': point, 'string': content})
    view.sel().clear()
    region = sublime.Region(point, point + len(content))
    view.sel().add(region)
    view.show(sublime.Region(point, point))


class CodeNavigator(object):
    """Base class for navigating within a particular file."""
    def __init__(self, target_filename, source_filename, content, source_row):
        self.target_filename = target_filename
        self.source_decls = list_decls(content, source_filename)
        self.source_decl = find_decl_for_row(self.source_decls, source_row)

        basename = os.path.basename(source_filename)
        relmodule, _ext = os.path.splitext(basename)
        if relmodule == '__init__':
            relmodule = ''
        self.template_vars = {'source_filename': source_filename,
                              'relmodule': relmodule,
                              'target_filename': target_filename}

    def traverse(self,
                 target_view,
                 source_name,
                 convert_name,
                 source_decls=None,
                 target_decls=None,
                 parent_target_decl=None,
                 match_mode='exact'):
        """Get the rows in the target view that correlate with a source name.

        This can traverse either top-level names or names inside a class.
        If source_decls and target_decls are not given, traverse the top-level
        names.

        Returns (target_decl or None, first_row, last_row). When not found,
        'first_row' indicates where the declaration should exist.
        """
        if source_decls is None:
            source_decls = self.source_decls
        if target_decls is None:
            target_decls = list_view_decls(target_view)

        target_name = convert_name(source_name)
        target_decl_map = dict((decl.name, decl) for decl in target_decls)
        matches = self.filter_targets(target_decl_map, target_name, match_mode)
        if matches:
            target_decl = matches[0]
            return target_decl, target_decl.first_row, target_decl.last_row

        # The target code does not exist.
        # Figure out where the new code belongs in the target file.
        max_row = 0
        min_row = None
        after = False
        for decl in source_decls:
            if decl.name == source_name:
                after = True
                continue

            matches = self.filter_targets(target_decl_map,
                                          convert_name(decl.name),
                                          match_mode)
            for target_decl in matches:
                if after:
                    # The new code belongs before this code.
                    if min_row is None:
                        min_row = target_decl.first_row - 1
                    else:
                        min_row = min(min_row, target_decl.first_row - 1)
                else:
                    # The new code belongs after this code.
                    max_row = max(max_row, target_decl.last_row + 1)

        if max_row:
            row = max_row
        elif min_row is not None:
            row = min_row
        else:
            if parent_target_decl is not None:
                # Add the new code to the end of the parent.
                row = parent_target_decl.last_row + 1
            else:
                # Add the new code to the end of the file.
                row, _col = target_view.rowcol(target_view.size())

        return None, row, row

    def filter_targets(self, decl_map, name, mode='exact'):
        """List the target decls that correspond with a source decl."""
        if mode == 'exact':
            decl = decl_map.get(name)
            if decl is not None:
                return [decl]
            else:
                return ()

        elif mode == 'prefix_under':
            prefix = name + '_'
            matches = []
            items = decl_map.items()
            items.sort()
            for key, decl in items:
                if key == name or key.startswith(prefix):
                    matches.append(decl)
            return matches

        else:
            raise ValueError("Unknown match mode: {0}".format(mode))


class TestCodeNavigator(CodeNavigator):
    """Navigate to test code and optionally generate it."""

    def __init__(self, generate, **kw):
        super(TestCodeNavigator, self).__init__(**kw)
        self.testgen = CustomTestGenerator(self.target_filename)
        self.generate = generate

    def goto(self, target_view):
        if self.source_decl is None:
            return

        decls = self.source_decl.get_path()
        if not decls:
            # No particular declaration was specified.
            return

        name = decls[0].name
        self.template_vars['name'] = name
        self.template_vars['testname'] = self.testgen.to_test_class_name(name)

        if self.generate and not target_view.size():
            # The test module is empty or doesn't exist, so create it.
            content = self.testgen.make_test_head(self.template_vars)
            insert_rows(target_view, 0, content)

        try:
            if isinstance(decls[0], ClassDecl):
                if len(decls) >= 2 and isinstance(decls[1], FuncDecl):
                    self.goto_method(target_view, decls[0], decls[1])
                else:
                    self.goto_class(target_view, decls[0])
            elif isinstance(decls[0], FuncDecl):
                self.goto_func(target_view, decls[0])
        except SyntaxError as e:
            show_syntax_error(e)
            return

    def goto_class(self, target_view, class_decl):
        sublime.status_message("SublimePythonGotoTest: "
                               "goto_class {0}".format(class_decl.name))

        convert_name = self.testgen.to_test_class_name
        target_decl, f_row, l_row = self.traverse(target_view,
                                                  class_decl.name,
                                                  convert_name)

        if target_decl is None and self.generate:
            content = self.testgen.make_class_test(self.template_vars)
            insert_rows(target_view, f_row, content)
        else:
            show_rows(target_view, f_row, l_row)

    def goto_func(self, target_view, func_decl):
        sublime.status_message("SublimePythonGotoTest: "
                               "goto_func {0}".format(func_decl.name))

        convert_name = self.testgen.to_test_class_name
        target_decl, f_row, l_row = self.traverse(target_view,
                                                  func_decl.name,
                                                  convert_name)

        if target_decl is None and self.generate:
            content = self.testgen.make_function_test(self.template_vars)
            insert_rows(target_view, f_row + 1, content)
        else:
            show_rows(target_view, f_row, l_row)

    def goto_method(self, target_view, class_decl, method_decl):
        sublime.status_message("SublimePythonGotoTest: "
                               "goto_method {0}.{1}".format(class_decl.name,
                                                            method_decl.name))

        convert_name = self.testgen.to_test_class_name
        target_class_decl, f_row, l_row = self.traverse(target_view,
                                                        class_decl.name,
                                                        convert_name)

        if target_class_decl is None and self.generate:
            content = self.testgen.make_class_test(self.template_vars)
            insert_rows(target_view, f_row, content)

            # Re-read the declarations.
            tup = self.traverse(target_view,
                                class_decl.name,
                                convert_name)
            target_class_decl, f_row, l_row = tup

        if target_class_decl is not None:
            tup = self.traverse(target_view=target_view,
                                source_name=method_decl.name,
                                convert_name=self.testgen.to_test_method_name,
                                source_decls=class_decl.children,
                                target_decls=target_class_decl.children,
                                parent_target_decl=target_class_decl,
                                match_mode='prefix_under')
            target_method_decl, f_row, l_row = tup

            if target_method_decl is None and self.generate:
                template_vars = {}
                template_vars.update(self.template_vars)
                template_vars['name'] = method_decl.name
                template_vars['testname'] = \
                    self.testgen.to_test_method_name(method_decl.name)
                template_vars['classname'] = class_decl.name
                content = self.testgen.make_method_test(template_vars)
                insert_rows(target_view, f_row, content, margin=1)
                return

        show_rows(target_view, f_row, l_row)


class MainCodeNavigator(CodeNavigator):
    def goto(self, target_view):
        pass


class CustomTestGenerator(object):
    """Use the lineage of __testgen__.py modules to generate tests."""

    func_names = ('to_test_class_name',
                  'to_test_method_name',
                  'make_test_head',
                  'make_function_test',
                  'make_class_test',
                  'make_method_test')

    def __init__(self, target_filename):
        modfiles = []

        fn = os.path.join(here, '__testgen__.py')
        modfiles.append(fn)

        parent = os.path.dirname(target_filename)
        while parent:
            fn = os.path.join(parent, '__testgen__.py')
            if os.path.exists(fn):
                modfiles.append(fn)
            next_parent = os.path.dirname(parent)
            if next_parent == parent:
                break
            else:
                parent = next_parent

        funcs = {}

        # Execute the most generic testgen module first so that more
        # specific modules can override as they see fit.
        for modfile in modfiles:
            execfile(modfile, funcs, funcs)

        # Now add the functions as methods of this object.
        for func_name in self.func_names:
            setattr(self, func_name, funcs[func_name])


def test_list_decls():
    # Ensure list_decls doesn't trip over various odd cases.
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
