import os


def list_dir_contents(srcdir):
    contents = set()
    for _, dirs, files in os.walk(srcdir):
        for d in dirs:
            contents.add(d)
        for f in files:
            contents.add(f)
    return contents
