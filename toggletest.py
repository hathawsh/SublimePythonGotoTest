
import codemunge
import os
import re
import sublime
import sublime_plugin


_builders = {}  # {filename: CodeBuilder}


class ToggleTestCommand(sublime_plugin.TextCommand):
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
                builder = MainCodeBuilder(content, row)
            else:
                sublime.status_message("toggle_test: {0} is not a test module."
                                       .format(fname))
                return
        else:
            # The file is the main code. Go to the test code.
            parent = os.path.join(dirname, 'tests')
            target = os.path.join(parent, 'test_' + basename)
            if not os.path.exists(parent):
                os.mkdir(parent)

            init_py = os.path.join(parent, '__init__.py')
            if not os.path.exists(init_py):
                # Create an empty __init__.py in the tests subdir.
                f = open(init_py, 'w')
                f.close()

            builder = TestCodeBuilder(content, row)

        win = view.window()
        view = win.open_file(target)

        if view.is_loading():
            _builders[os.path.abspath(target)] = builder
        else:
            builder.goto_target(view)


class Listener(sublime_plugin.EventListener):
    def on_load(self, view):
        fn = os.path.abspath(view.file_name())
        builder = _builders.get(fn)
        if builder is not None:
            del _builders[fn]
            builder.goto_target(view)


def get_decl_map(view):
    content = view.substr(sublime.Region(0, view.size()))
    decls = codemunge.list_decls(content)
    return dict((decl.name, decl) for decl in decls)


def to_test_name(name):
    if name[:1].upper() == name[:1]:
        return 'Test{0}'.format(name)
    else:
        return 'Test_{0}'.format(name)


def to_main_name(name):
    if name.startswith('Test_'):
        return name[5:]
    elif name.startswith('Test'):
        return name[4:]
    else:
        return None


def show_row(view, row):
    point = view.text_point(row, 0)
    line = view.substr(view.line(point))
    match = re.match(r'\s+', line)
    if match is not None:
        point += len(match.group(0))
    view.sel().clear()
    view.sel().add(sublime.Region(point))
    view.show(point)


class CodeBuilder(object):
    def __init__(self, content, row):
        self.source_decls = codemunge.list_decls(content)
        self.source_decl = codemunge.find_decl_for_row(self.source_decls, row)

    def lineage(self):
        decl = self.source_decl
        while decl is not None and not isinstance(decl, codemunge.ModuleDecl):
            yield decl
            decl = decl.parent_ref()

    def get_correlated_row(self, target_view, source_name, convert_name):
        """Get the row in the target view that correlates with the source name.

        convert_name is a function that converts a source_name to
        the correlated target_name.

        Returns (row, found). When not found, returns the row where it should
        have been found.
        """
        target_decl_map = get_decl_map(target_view)
        target_name = convert_name(source_name)
        decl = target_decl_map.get(target_name)
        if decl is not None:
            return decl.first_row + 1, True

        # The target code does not exist.
        # Figure out where the new code belongs in the file.
        row = 0
        for source_decl in self.source_decls:
            if source_decl.name == source_name:
                break
            target_decl = target_decl_map.get(convert_name(source_decl.name))
            if target_decl is not None:
                # The new code belongs somewhere after this code.
                row = max(row, target_decl.last_row)

        if not row:
            # Place the new code where the first block of code already is.
            row = min(decl.first_row for decl in target_decl_map.itervalues())

        return row, False


class TestCodeBuilder(CodeBuilder):
    """Build and navigate to test code."""

    def goto_target(self, target_view):
        decls = list(self.lineage())
        decls.reverse()
        if not decls:
            # No particular declaration was specified.
            return

        if isinstance(decls[0], codemunge.ClassDecl):
            if len(decls) >= 2 and isinstance(decls[1], codemunge.FuncDecl):
                self.goto_method(target_view, decls[0].name, decls[1].name)
            else:
                self.goto_class(target_view, decls[0].name)
        elif isinstance(decls[0], codemunge.FuncDecl):
            self.goto_func(target_view, decls[0].name)

    def goto_class(self, target_view, class_name):
        sublime.status_message("toggle_test: goto_class({0!r})"
                               .format(class_name))

        row, found = self.get_correlated_row(target_view,
                                             class_name,
                                             to_test_name)

        if not found:
            # TODO: generate the test code.
            pass

        show_row(target_view, row)

    def goto_method(self, target_view, class_name, method_name):
        sublime.status_message("toggle_test: goto_method({0!r}, {1!r})"
                               .format(class_name, method_name))

    def goto_func(self, target_view, func_name):
        sublime.status_message("toggle_test: goto_func({0!r})"
                               .format(func_name))

        row, found = self.get_correlated_row(target_view,
                                             func_name,
                                             to_test_name)

        if not found:
            # TODO: generate the test code.
            pass

        show_row(target_view, row)


class MainCodeBuilder(CodeBuilder):
    def goto_target(self, target_view):
        pass
