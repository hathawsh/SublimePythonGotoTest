"""

Generate test stubs from templates. Used by SublimePythonGotoTest.

This particular __testgen__.py is designed for writing tests of code that uses
the Pyramid framework, but you can easily customize this by adding your own
__testgen__.py to your source tree. The SublimePythonGotoTest plugin looks for
__testgen__.py in your test directory and all of its parent directories. It
calls these four functions:

    - make_test_head(source_filename, relmodule)
    - make_function_test(source_filename, relmodule, name, testname)
    - make_class_test(source_filename, relmodule, name, testname)
    - make_method_test(source_filename, relmodule, name, testname, classname)

More parameters may be added in the future, so be sure to add ``**kw`` or
similar to the function signatures.

Note that this code will be executed by Sublime Text's internal Python
interpreter, so you should not try to import from your code.

"""


test_head_template = '''\
from pyramid import testing

try:
    # Python < 2.7
    import unittest2 as unittest  # NOQA
except ImportError:
    # Python >= 2.7
    import unittest  # NOQA
'''


def make_test_head(source_filename, relmodule, **kw):
    return test_head_template.format(**locals())


function_test_template = """\
class {testname}(unittest.TestCase):

    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def _call(self, *args, **kw):
        from ..{relmodule} import {name}
        return {name}(*args, **kw)
"""


def make_function_test(source_filename, relmodule, name, testname, **kw):
    return function_test_template.format(**locals())


class_test_template = """\
class {testname}(unittest.TestCase):

    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    @property
    def _class(self):
        from ..{relmodule} import {name}
        return {name}

    def _make(self):
        return self._class()
"""


def make_class_test(source_filename, relmodule, name, testname, **kw):
    return class_test_template.format(**locals())


method_test_template = """\
    def {testname}(self):
        obj = self._make()
"""


def make_method_test(source_filename, relmodule, name, testname, classname,
                     **kw):
    return method_test_template.format(**locals())
