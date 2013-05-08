
import codemunge
import os
import sublime
import sublime_plugin

_deferred = {}  # {filename: CodeNav}


class GotoTestCommand(sublime_plugin.TextCommand):
    """Go to the unit test for this Python code or vice-versa"""

    generate = False

    def run(self, edit):
        view = self.view
        fname = view.file_name()
        if not fname:
            sublime.status_message("PythonGotoTest: No file name given.")
            return

        dirname, basename = os.path.split(fname)
        name, ext = os.path.splitext(basename)
        if ext != '.py':
            sublime.status_message("PythonGotoTest: for .py files only.")
            return

        content = view.substr(sublime.Region(0, view.size()))
        point = view.sel()[0].begin()
        row, _col = view.rowcol(point)

        if os.path.basename(dirname) == 'tests':
            if basename.startswith('test_'):
                # The file is test code. Go to the main code.
                parent = os.path.dirname(dirname)
                target = os.path.join(parent, basename[5:])
                try:
                    nav = MainCodeNavigator(target_filename=target,
                                            source_filename=fname,
                                            content=content,
                                            source_row=row)
                except SyntaxError as e:
                    show_syntax_error(e)
                    return
            else:
                sublime.status_message("PythonGotoTest: {0} is "
                                       "not a test module.".format(fname))
                return
        else:
            # The file is the main code. Go to the test code.
            parent = os.path.join(dirname, 'tests')
            test_fn = 'test_' + basename
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
    return codemunge.list_decls(content, view.file_name())


def to_test_class_name(name):
    if name[:1].upper() == name[:1]:
        return 'Test{0}'.format(name)
    else:
        return 'Test_{0}'.format(name)


def to_test_method_name(name):
    if name == '__init__':
        name = 'ctor'
    return 'test_{0}'.format(name)


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

    edit = view.begin_edit('insert_test')
    view.insert(edit, point, content)
    view.end_edit(edit)
    view.sel().clear()
    region = sublime.Region(point, point + len(content))
    view.sel().add(region)
    view.show(sublime.Region(point, point))


class CodeNavigator(object):
    def __init__(self, target_filename, source_filename, content, source_row):
        self.source_decls = codemunge.list_decls(content, source_filename)
        self.source_decl = codemunge.find_decl_for_row(self.source_decls,
                                                       source_row)

        basename = os.path.basename(target_filename)
        relmodule, _ext = os.path.splitext(basename)
        if relmodule == '__init__':
            relmodule = ''
        self.template_vars = {'relmodule': relmodule}

    def traverse(self,
                 target_view,
                 source_name,
                 convert_name,
                 source_decls=None,
                 target_decls=None,
                 parent_target_decl=None,
                 match_mode='exact'):
        """Get the rows in the target view that correlate with a source name.

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

        try:
            if isinstance(decls[0], codemunge.ClassDecl):
                if len(decls) >= 2 and isinstance(decls[1], codemunge.FuncDecl):
                    self.goto_method(target_view, decls[0], decls[1])
                else:
                    self.goto_class(target_view, decls[0])
            elif isinstance(decls[0], codemunge.FuncDecl):
                self.goto_func(target_view, decls[0])
        except SyntaxError as e:
            show_syntax_error(e)
            return

    def goto_class(self, target_view, class_decl):
        sublime.status_message("PythonGotoTest: goto_class {0}"
                               .format(class_decl.name))

        target_decl, f_row, l_row = self.traverse(target_view,
                                                  class_decl.name,
                                                  to_test_class_name)

        if target_decl is None and self.generate:
            content = self.testgen.make_class_test(self.template_vars)
            insert_rows(target_view, f_row, content)
        else:
            show_rows(target_view, f_row, l_row)

    def goto_func(self, target_view, func_decl):
        sublime.status_message("PythonGotoTest: goto_func {0}"
                               .format(func_decl.name))

        target_decl, f_row, l_row = self.traverse(target_view,
                                                  func_decl.name,
                                                  to_test_class_name)

        if target_decl is None and self.generate:
            content = self.testgen.make_function_test(self.template_vars)
            insert_rows(target_view, f_row + 1, content)
        else:
            show_rows(target_view, f_row, l_row)

    def goto_method(self, target_view, class_decl, method_decl):
        sublime.status_message("PythonGotoTest: goto_method {0}.{1}"
                               .format(class_decl.name, method_decl.name))

        target_class_decl, f_row, l_row = self.traverse(target_view,
                                                        class_decl.name,
                                                        to_test_class_name)

        if target_class_decl is None and self.generate:
            content = self.testgen.make_class_test(self.template_vars)
            insert_rows(target_view, f_row, content)

            # Re-read the declarations.
            tup = self.traverse(target_view,
                                class_decl.name,
                                to_test_class_name)
            target_class_decl, f_row, l_row = tup

        if target_class_decl is not None:
            tup = self.traverse(target_view=target_view,
                                source_name=method_decl.name,
                                convert_name=to_test_method_name,
                                source_decls=class_decl.children,
                                target_decls=target_class_decl.children,
                                parent_target_decl=target_class_decl,
                                match_mode='prefix_under')
            target_method_decl, f_row, l_row = tup

            if target_method_decl is None and self.generate:
                template_vars = {}
                template_vars.update(template_vars)
                template_vars['class'] = class_decl.name
                template_vars['name'] = method_decl.name
                template_vars['method'] = to_test_method_name(method_decl.name)
                content = self.testgen.make_method_test(template_vars)
                insert_rows(target_view, f_row, content, margin=1)
                return

        show_rows(target_view, f_row, l_row)


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

    method_test_template = """\
    @unittest.skip('stub test of method {name}')
    def {method}(self):
        pass
"""

    def make_test_head(self, template_vars):
        return self.test_head_template.format(**template_vars)

    def make_function_test(self, template_vars):
        return self.function_test_template.format(**template_vars)

    def make_class_test(self, template_vars):
        return self.class_test_template.format(**template_vars)

    def make_method_test(self, template_vars):
        return self.method_test_template.format(**template_vars)
