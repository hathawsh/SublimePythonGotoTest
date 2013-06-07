"""

Generate test stubs from templates. Used by SublimePythonGotoTest.

This particular __testgen__.py is designed for writing tests of code that uses
the Pyramid framework, but you can easily customize this by adding your own
__testgen__.py to your source tree. The SublimePythonGotoTest plugin looks for
__testgen__.py in your test directory and all of its parent directories. It
calls these functions:

    - to_test_class_name(name)

    - to_test_method_name(name)

    - make_test_head(template_vars)

        - template_vars contains at least 'source_filename' and 'relmodule'.

    - make_function_test(template_vars)

        - template_vars contains at least 'source_filename', 'relmodule',
          'name', and 'testname'.

    - make_class_test(template_vars)

        - template_vars contains at least 'source_filename', 'relmodule',
          'name', and 'testname'.

    - make_method_test(template_vars)

        - template_vars contains at least 'source_filename', 'relmodule',
          'name', 'testname', and 'classname'.

Note that this module is executed by Sublime Text's internal Python
interpreter, so you should not try to import from your code in __testgen__.py.
"""


def to_test_class_name(name):
    """Translate a class or function name to a test class name."""
    if name[:1].isupper():
        return 'Test{0}'.format(name)
    else:
        return 'Test_{0}'.format(name)


def to_test_method_name(name):
    """Translate a method name to a test method name."""
    if name == '__init__':
        name = 'ctor'
    elif name == '__call__':
        name = 'call'
    return 'test_{0}'.format(name)


test_head_template = '''\
from pyramid import testing

try:
    # Python < 2.7
    import unittest2 as unittest  # NOQA
except ImportError:
    # Python >= 2.7
    import unittest  # NOQA
'''


def make_test_head(template_vars):
    return test_head_template.format(**template_vars)


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


def make_function_test(template_vars):
    return function_test_template.format(**template_vars)


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


def make_class_test(template_vars):
    return class_test_template.format(**template_vars)


method_test_template = """\
    def {testname}(self):
        obj = self._make()
        obj.{name}()
"""


def make_method_test(template_vars):
    return method_test_template.format(**template_vars)
