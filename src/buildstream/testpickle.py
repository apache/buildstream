import multiprocessing.reduction


class _C:
    def f(self):
        pass


def test_pickle(*args, **kwargs):
    import bdb
    try:
        _test_pickle(*args, **kwargs)
    except bdb.BdbQuit:
        raise
    except Exception as e:
        breakpoint()
        raise


def _test_pickle(x, indent=0, visited=None):

    def prefix_print(*messages):
        print(".   " * indent + f"({type(x).__name__}):", *messages)

    if visited is None:
        visited = set()

    if id(x) in visited:
        prefix_print(".. skipping already visited")
        return

    visited.add(id(x))

    import bdb

    try:
        test_pickle_direct(x)
    except bdb.BdbQuit:
        raise
    except Exception as e:
        prefix_print(f'({x}): does not pickle, recursing.', str(e), repr(e), ':.:')
    else:
        prefix_print(f'({x}): does pickle, skipping.')
        return

    if type(x) == type(_C().f):
        prefix_print(f'method {x.__func__.__name__}')
        try:
            if x.__self__ is None:
                value = x.__class__
            else:
                value = x.__self__
            _test_pickle(value, indent + 1, visited)
        except:
            prefix_print(f"while pickling item method {x.__func__.__name__}: '{x}'.")
            raise

    if type(x).__name__ in ['method', 'instancemethod']:
        prefix_print(".. skipping method")
        return

    if type(x).__name__ in ['list', 'tuple', 'set']:
        prefix_print('... len', len(x))
        for key, value in enumerate(x):
            prefix_print(f'[{key}]')
            try:
                _test_pickle(value, indent + 1, visited)
            except:
                prefix_print(f"while pickling item {key}: {type(x).__name__}: '{x}'.")
                raise
        return

    # if type(x).__name__ == 'function':
    #     prefix_print("function?")
    #     raise Exception()

    # if type(x).__name__ == 'module':
    #     prefix_print(".. module")
    #     test_pickle_direct(x)
    #     return

    # TODO: make these work properly.
    # if type(x).__name__ in ['SourceFactory', 'ElementFactory', 'Environment']:
    #     prefix_print(".. skipping")
    #     return
    if type(x).__name__ in ['_UnixSelectorEventLoop', 'AuthenticationString', 'SyncManager']:
        prefix_print(".. skipping")
        return

    if type(x).__name__ == 'dict':
        prefix_print("...", x.keys())
        for key, value in x.items():
            prefix_print(f'[{key}]')
            try:
                _test_pickle(value, indent + 1, visited)
            except:
                prefix_print(f"while pickling ['{key}'].")
                raise
        return

    # TODO: we need to make the generators work too, or ideally replace them.
    # if type(x).__name__ == 'generator':
    #     prefix_print(".. skipping generator")
    #     return

    # TODO: we need to make the weakrefs work properly.
    if type(x).__name__ == 'weakref':
        prefix_print(".. dereferencing weakref")
        try:
            _test_pickle(x(), indent, visited)
        except:
            prefix_print(f"while pickling weakref {x}.")
            raise
        return

    try:
        value = x.__getstate__()
    except AttributeError:
        pass
    else:
        prefix_print("... __getstate__")
        try:
            _test_pickle(value, indent + 1, visited)
        except:
            prefix_print(f"while pickling a __getstate__.")
            raise
        return

    try:
        x.__dict__
    except AttributeError:
        pass
    else:
        prefix_print("...", x.__dict__.keys())
        for key, value in x.__dict__.items():
            prefix_print(f'__dict__["{key}"]')
            try:
                _test_pickle(value, indent + 1, visited)
            except:
                prefix_print(f"while pickling member ['{key}'].")
                raise
        return

    try:
        x.__slots__
    except AttributeError:
        pass
    else:
        prefix_print("...", x.__slots__)
        for key in x.__slots__:
            value = getattr(x, key)
            prefix_print(f'__slots__["{key}"]')
            try:
                _test_pickle(value, indent + 1, visited)
            except:
                prefix_print(f"while pickling member '{key}'.")
                raise
        return

    prefix_print(x)
    test_pickle_direct(x)


def test_pickle_direct(x):
    import io
    import pickle
    import multiprocessing.reduction

    # Note that we should expect to see this complaint if we are not in a
    # multiprocessing spawning_popen context, this will be fine when we're
    # actually spawning:
    #
    #     Pickling an AuthenticationString object is disallowed for
    #     security reasons.
    #
    # https://github.com/python/cpython/blob/master/Lib/multiprocessing/process.py#L335
    #

    # Suppress the complaint by pretending we're in a spawning context.
    # https://github.com/python/cpython/blob/a8474d025cab794257d2fd0bea67840779b9351f/Lib/multiprocessing/popen_spawn_win32.py#L91
    import multiprocessing.context
    multiprocessing.context.set_spawning_popen("PPPPPopen")

    data = io.BytesIO()

    # Try to simulate what multiprocessing will do.
    # https://github.com/python/cpython/blob/master/Lib/multiprocessing/reduction.py
    try:
        multiprocessing.reduction.dump(x, data)
    except:
        # breakpoint()
        raise
    finally:
        multiprocessing.context.set_spawning_popen(None)

    return data
