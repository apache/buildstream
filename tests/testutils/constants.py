# Constants used during BuildStream tests.


# Timeout for short interactive operations (in seconds).
#
# Use this for operations that are expected to finish within a short amount of
# time. Like `bst init`, `bst show` on a small project.
PEXPECT_TIMEOUT_SHORT = 30


# Timeout for longer interactive operations (in seconds).
#
# Use this for operations that are expected to take longer amounts of time,
# like `bst build` on a small project.
PEXPECT_TIMEOUT_LONG = 300
