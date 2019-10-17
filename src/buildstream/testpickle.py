import copyreg
import io
import pickle


class _C:
    def f(self):
        pass


class TestPickler:
    def __init__(self):
        self.dispatch_table = copyreg.dispatch_table.copy()
        self.visited = set()

    def test_dump(self, obj):
        import bdb
        try:
            self._test_pickle(obj)
        except bdb.BdbQuit:
            raise
        except Exception:
            breakpoint()
            raise

    def _pickle(self, obj):
        data = io.BytesIO()
        pickler = pickle.Pickler(data)
        pickler.dispatch_table = self.dispatch_table.copy()
        pickler.dump(obj)

    def _test_pickle(self, x, indent=0):

        if indent > 50:
            print()
            print('*' * 80)
            print("Indent level too high:", indent)
            print('*' * 80)
            print()
            raise Exception("Indent level too high:", indent)

        def prefix_print(*messages):
            print(".   " * indent + f"({type(x).__name__}):", *messages)

        if id(x) in self.visited:
            prefix_print(".. skipping already visited")
            return

        self.visited.add(id(x))

        import bdb
        try:
            self._pickle(x)
        except bdb.BdbQuit:
            raise
        except Exception as e:
            prefix_print(f'({x}): does not pickle, recursing.', str(e), repr(e), ':.:')
        else:
            prefix_print(f'({x}): does pickle, skipping.')
            return

        if type(x) in self.dispatch_table:
            unreducer, args, state = self.dispatch_table[type(x)](x)
            prefix_print(f'({type(x)}): is in the dispatch_table, pickling reduced state.')
            self._test_pickle(state, indent + 1)
            return

        if type(x) == type(_C().f):
            prefix_print(f'method {x.__func__.__name__}')
            try:
                if x.__self__ is None:
                    value = x.__class__
                else:
                    value = x.__self__
                self._test_pickle(value, indent + 1)
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
                    self._test_pickle(value, indent + 1)
                except:
                    prefix_print(f"while pickling item {key}: {type(x).__name__}: '{x}'.")
                    raise
            return

        # if type(x).__name__ == 'function':
        #     prefix_print("function?")
        #     raise Exception()

        # if type(x).__name__ == 'module':
        #     prefix_print(".. module")
        #     pickle_func(x)
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
                    self._test_pickle(value, indent + 1)
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
                self._test_pickle(x(), indent)
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
                self._test_pickle(value, indent + 1)
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
                    self._test_pickle(value, indent + 1)
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
                    self._test_pickle(value, indent + 1)
                except:
                    prefix_print(f"while pickling member '{key}'.")
                    raise
            return

        print()
        print('*' * 80)
        print("!!! Unhandled pickle case:", x, type(x))
        print('*' * 80)
        print()
        # raise Exception("Unhandled pickle case")
        # prefix_print(x)
        # self._pickle(x)


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
