import os
import string


def element_ref_name(element_name):
    # Replace path separator and chop off the .bst suffix
    element_name = os.path.splitext(element_name.replace(os.sep, '-'))[0]

    # replace other sybols with '_'
    valid_chars = string.digits + string.ascii_letters + '-._'
    return ''.join([
        x if x in valid_chars else '_'
        for x in element_name
    ])
