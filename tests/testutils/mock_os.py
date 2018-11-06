from contextlib import contextmanager
import os


# MockAttributeResult
#
# A class to take a dictionary of kwargs and make them accessible via
# attributes of the object.
#
class MockAttributeResult(dict):
    __getattr__ = dict.get


# mock_statvfs():
#
# Gets a function which mocks statvfs and returns a statvfs result with the kwargs accessible.
#
# Returns:
#    func(path) -> object: object will have all the kwargs accessible via object.kwarg
#
# Example:
#    statvfs = mock_statvfs(f_blocks=10)
#    result = statvfs("regardless/of/path")
#    assert result.f_blocks == 10 # True
def mock_statvfs(**kwargs):
    def statvfs(path):
        return MockAttributeResult(kwargs)
    return statvfs


# monkey_patch()
#
# with monkey_patch("statvfs", custom_statvfs):
#    assert os.statvfs == custom_statvfs # True
# assert os.statvfs == custom_statvfs # False
#
@contextmanager
def monkey_patch(to_patch, patched_func):
    orig = getattr(os, to_patch)
    setattr(os, to_patch, patched_func)
    try:
        yield
    finally:
        setattr(os, to_patch, orig)
