import subprocess


def apply(file, patch):
    try:
        subprocess.check_output(["patch", file, patch])
    except subprocess.CalledProcessError as e:
        message = "Patch failed with exit code {}\n Output:\n {}".format(e.returncode, e.output)
        print(message)
        raise


def remove(file, patch):
    try:
        subprocess.check_output(["patch", "--reverse", file, patch])
    except subprocess.CalledProcessError as e:
        message = "patch --reverse failed with exit code {}\n Output:\n {}".format(e.returncode, e.output)
        print(message)
        raise
