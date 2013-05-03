
import codemunge
import os
import sublime
import sublime_plugin


class ToggleTestCommand(sublime_plugin.TextCommand):

    def run(self, edit):
        fname = self.view.file_name()
        if not fname:
            sublime.status_message("toggle_test: No file name given")
            return

        dirname, basename = os.path.split(fname)
        name, ext = os.path.splitext(basename)
        if ext != '.py':
            sublime.status_message("toggle_test: for .py files only.")
            return

        content = self.view.substr(0)
        point = self.view.sel()[0].begin()
        row, _col = self.view.rowcol(point)

        if os.path.basename(dirname) == 'tests':
            if basename.startswith('test_'):
                # The file is a test. Go to the main code.
                parent = os.path.dirname(dirname)
                target = os.path.join(parent, basename[5:])
                target_row = prepare_main_code(content, row, target)
            else:
                sublime.status_message("toggle_test: {0} is not a test module"
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

            target_row = prepare_test_code(content, row, target)

        win = self.view.window()
        win.open_file(target, target_row)


def prepare_test_code(main_content, main_row, test_file):
    return 0


def prepare_main_code(test_content, test_row, main_file):
    return 0
