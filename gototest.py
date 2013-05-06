
import codemunge
import os
import re
import sublime
import sublime_plugin

_deferred = {}  # {filename: CodeNav}


class GotoTestCommand(sublime_plugin.TextCommand):
    generate = False

    def run(self, edit):
        view = self.view
        fname = view.file_name()
        if not fname:
            sublime.status_message("toggle_test: No file name given.")
            return

        dirname, basename = os.path.split(fname)
        name, ext = os.path.splitext(basename)
        if ext != '.py':
            sublime.status_message("toggle_test: for .py files only.")
            return

        content = view.substr(sublime.Region(0, view.size()))
        point = view.sel()[0].begin()
        row, _col = view.rowcol(point)

        if os.path.basename(dirname) == 'tests':
            if basename.startswith('test_'):
                # The file is a test. Go to the main code.
                parent = os.path.dirname(dirname)
                target = os.path.join(parent, basename[5:])
                nav = MainCodeNavigator(target, content, row)
            else:
                sublime.status_message("toggle_test: {0} is not a test module."
                                       .format(fname))
                return
        else:
            # The file is the main code. Go to the test code.
            nav = TestCodeNavigator(fname, content, row,
                                    generate=self.generate)

            parent = os.path.join(dirname, 'tests')
            test_fn = 'test_' + basename
            target = os.path.join(parent, test_fn)
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
    generate = True


class Listener(sublime_plugin.EventListener):
    def on_load(self, view):
        fn = os.path.abspath(view.file_name())
        nav = _deferred.get(fn)
        if nav is not None:
            del _deferred[fn]
            nav.goto(view)


def list_view_decls(view):
    content = view.substr(sublime.Region(0, view.size()))
    return codemunge.list_decls(content)


def to_test_class_name(name):
    if name[:1].upper() == name[:1]:
        return 'Test{0}'.format(name)
    else:
        return 'Test_{0}'.format(name)


def to_test_method_name(name):
    return 'test_{0}'.format(name)


def to_main_name(name):
    if name.startswith('Test_'):
        return name[5:]
    elif name.startswith('Test'):
        return name[4:]
    else:
        return None


def show_row(view, row):
    """Position the cursor on a row in a view."""
    point = view.text_point(row, 0)
    line = view.substr(view.line(point))
    match = re.match(r'\s+', line)
    if match is not None:
        point += len(match.group(0))
    view.sel().clear()
    view.sel().add(sublime.Region(point))
    view.show(point)


def insert_rows(view, row, content, margin=2):
    point = view.text_point(row, 0)

    if margin:
        if row > 0:
            # Add blank lines before.
            region = sublime.Region(max(0, point - margin), point)
            text_before = view.substr(region)
            blanks = 0
            for c in reversed(text_before):
                if c == '\n':
                    blanks += 1
                else:
                    break
            if blanks < margin:
                content = '\n' * (margin - blanks) + content

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

    edit = view.begin_edit('insert_test')
    view.insert(edit, point, content)
    view.end_edit(edit)
    view.sel().clear()
    region = sublime.Region(point, point + len(content))
    view.sel().add(region)
    view.show(region)


class CodeNavigator(object):
    def __init__(self, filename, content, source_row):
        self.source_decls = codemunge.list_decls(content)
        self.source_decl = codemunge.find_decl_for_row(self.source_decls,
                                                       source_row)

        basename = os.path.basename(filename)
        relmodule, _ext = os.path.splitext(basename)
        if relmodule == '__init__':
            relmodule = ''
        self.template_vars = {'relmodule': relmodule}

    def traverse_top(self, target_view, top_source_name, convert_name):
        """Get the row in the target view that correlates with a source name.

        Returns (target_decl or None, row). When not found, 'row'
        indicates where the declaration should exist.
        """
        target_decls = list_view_decls(target_view)
        target_decl_map = dict((decl.name, decl) for decl in target_decls)
        target_name = convert_name(top_source_name)
        target_decl = target_decl_map.get(target_name)
        if target_decl is not None:
            return target_decl, target_decl.first_row + 1

        # The target code does not exist.
        # Figure out where the new code belongs in the file.
        row = 0
        for decl in self.source_decls:
            if decl.name == top_source_name:
                # Ignore the rest of the source declarations.
                break
            target_decl = target_decl_map.get(convert_name(decl.name))
            if target_decl is not None:
                # The new code belongs after this code.
                row = max(row, target_decl.last_row + 1)

        if not row:
            # Add the new code to the end.
            row, _col = target_view.rowcol(target_view.size())

        return None, row


class TestCodeNavigator(CodeNavigator):
    """Navigate to test code and optionally generate it."""

    def __init__(self, filename, content, row, generate):
        super(TestCodeNavigator, self).__init__(filename, content, row)
        self.testgen = BasicTestGenerator()
        self.generate = generate

    def goto(self, target_view):
        decls = self.source_decl.get_path()
        if not decls:
            # No particular declaration was specified.
            return

        name = decls[0].name
        self.template_vars['name'] = name
        self.template_vars['testname'] = to_test_class_name(name)

        if self.generate and not target_view.size():
            content = self.testgen.make_test_head(self.template_vars)
            insert_rows(target_view, 0, content)

        if isinstance(decls[0], codemunge.ClassDecl):
            if len(decls) >= 2 and isinstance(decls[1], codemunge.FuncDecl):
                self.goto_method(target_view, decls[0], decls[1])
            else:
                self.goto_class(target_view, decls[0])
        elif isinstance(decls[0], codemunge.FuncDecl):
            self.goto_func(target_view, decls[0])

    def goto_class(self, target_view, class_decl):
        sublime.status_message("toggle_test: goto_class {0}"
                               .format(class_decl.name))

        target_decl, row = self.traverse_top(target_view,
                                             class_decl.name,
                                             to_test_class_name)

        if target_decl is None and self.generate:
            content = self.testgen.make_class_test(self.template_vars)
            insert_rows(target_view, row, content)
        else:
            show_row(target_view, row)

    def goto_func(self, target_view, func_decl):
        sublime.status_message("toggle_test: goto_func {0}"
                               .format(func_decl.name))

        target_decl, row = self.traverse_top(target_view,
                                             func_decl.name,
                                             to_test_class_name)

        if target_decl is None and self.generate:
            content = self.testgen.make_function_test(self.template_vars)
            insert_rows(target_view, row, content)
        else:
            show_row(target_view, row)

    def goto_method(self, target_view, class_decl, method_decl):
        sublime.status_message("toggle_test: goto_method {0}.{1}"
                               .format(class_decl.name, method_decl.name))

        target_class_decl, row = self.traverse_top(target_view,
                                                   class_decl.name,
                                                   to_test_class_name)

        if target_class_decl is None and self.generate:
            content = self.testgen.make_class_test(self.template_vars)
            insert_rows(target_view, row, content)

            # Re-read the declarations.
            target_class_decl, row = self.traverse_top(target_view,
                                                       class_decl.name,
                                                       to_test_class_name)

        if target_class_decl is not None:
            tup = self.traverse_method(target_class_decl.children,
                                       method_decl.name,
                                       to_test_method_name)
            target_method_decl, row, found = tup

            if target_method_decl is None and self.generate:
                template_vars = {}
                template_vars.update(template_vars)
                template_vars['name'] = method_decl.name
                template_vars['method'] = to_test_method_name(method_decl.name)
                content = self.testgen.make_method_test(template_vars)
                insert_rows(target_view, row, content, margin=1)

        show_row(target_view, row)


class MainCodeNavigator(CodeNavigator):
    def goto(self, target_view):
        pass


class BasicTestGenerator(object):
    test_head_template = '''\
try:
    import unittest2 as unittest
except ImportError:
    import unittest

'''

    function_test_template = """\
class {testname}(unittest.TestCase):

    def _call(self, *args, **kw):
        from ..{relmodule} import {name}
        return {name}(*args, **kw)

"""

    class_test_template = """\
class {testname}(unittest.TestCase):

    @property
    def _class(self):
        from ..{relmodule} import {name}
        return {name}

    def _make(self):
        return self._class()

"""

    def make_test_head(self, template_vars):
        return self.test_head_template.format(**template_vars)

    def make_function_test(self, template_vars):
        return self.function_test_template.format(**template_vars)

    def make_class_test(self, template_vars):
        return self.class_test_template.format(**template_vars)
