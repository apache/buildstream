Multi-venv experiment
=====================

This is an experiment to test the feasability of supporting a venv per plugin,
all running under the same interpreter.

It shows:

  * Installing two separate venvs with different dependency versions
  * Running an interpretor which loads a plugin in both separate
    venvs (it could even be the same plugin, and need not be a
    "BuildStream" plugin, but some python module loaded on demand)
  * Prove that we infact have separation (perhaps by having the plugin
    just print the versions of it's dependencies).

The approach taken in this experiment is to push all modules required by the
plugin into a PluginBase space.

Major problems discovered
-------------------------

- We don't override `sys.modules`, so this in jinja2 v2.10 won't work: `del
  sys.modules['jinja2._identifier']`. A first attempt to override `sys.modules`
  resulted in mysterious failures not detailed here.

- Relative-imports work in a way that doesn't seem to be obvious, which is
  incompatible with the hack to rewrite top-level imports. See the
  `import_override` function for more details.

- Global imports don't seem to work with pure PluginBase, e.g. jinja2
  itself will do `from jinja2.environment import Environment, Template` in its
  `__init__.py`, which fails. This is overcome with the `import_override`
  hackery in the experiment.

- the `jinja2.__version__` reported by the plugin is actually the version of
  `pluginbase` instead. Interestingly the `jinja2.__version__` reported in the
  main app is different.

- the `jinja2.evalcontextfilter` accessed by the plugin is different from the
  one accessed in the main app. That's probably for the same reason as the
  above point.

Setup
-----

Create a Python venv for each subdirectory, e.g.

    python3 -m venv ~/PyVenv/notbuildstream
    python3 -m venv ~/PyVenv/notbstalphaelement
    python3 -m venv ~/PyVenv/notbstbetaelement
    python3 -m venv ~/PyVenv/notbstgammaelement

Then, for each directory:

- Activate the appropriate venv. e.g. `. ~/PyVenv/notbuildstream/bin/activate`.
- For each subdirectory, `pip install SUBDIRECTORY`. Don't use `-e`, as it
  seems that `.egg-link`s are a separate case that need special consideration.

Make sure that the reference to `lib/python3.7/site-packages` in
`notbuildstream.py` is fixed up as appropriate for your venvs.

Running
-------

Enter the venv for `notbuildstream`, and invoke it with the paths to the other
venvs, e.g.

    notbst ~/PyVenv/ ~/PyVenv/notbst{alpha,beta,gamma}element

You should see somthing like:

```
venv: /Users/jevripiotis/PyVenv/notbstalphaelement
Alpha
jinja2.__version__: 1.0.0
jinja2.evalcontextfilter: None
main: jinja2: <module 'pluginbase._internalspace._sp5d362f8c6220a8c7f6ec3263825004f6.jinja2' from '/Users/jevripiotis/PyVenv/notbstalphaelement/lib/python3.7/site-packages/jinja2/__init__.py'>
main: jinja2.__version__: 2.8
main: jinja2.__file__: /Users/jevripiotis/PyVenv/notbstalphaelement/lib/python3.7/site-packages/jinja2/__init__.py
main: Has evalcontextfilter: <function evalcontextfilter at 0x10b66c9d8>

venv: /Users/jevripiotis/PyVenv/notbstbetaelement
Beta
jinja2.__version__: 1.0.0
jinja2.evalcontextfilter: None
main: jinja2: <module 'pluginbase._internalspace._sp97ff7e741eeaeaf9c282906561d1b456.jinja2' from '/Users/jevripiotis/PyVenv/notbstbetaelement/lib/python3.7/site-packages/jinja2/__init__.py'>
main: jinja2.__version__: unknown
main: jinja2.__file__: /Users/jevripiotis/PyVenv/notbstbetaelement/lib/python3.7/site-packages/jinja2/__init__.py
main: Has evalcontextfilter: None

venv: /Users/jevripiotis/PyVenv/notbstgammaelement
Traceback (most recent call last):
  File "/Users/jevripiotis/PyVenv/notbuildstream/bin/notbst", line 11, in <module>
    load_entry_point('notbuildstream', 'console_scripts', 'notbst')()
--- 8< --- snip long stacktrace --- 8< ---
  File "/Users/jevripiotis/PyVenv/notbstgammaelement/lib/python3.7/site-packages/jinja2/lexer.py", line 50, in <module>
    del sys.modules['jinja2._identifier']
KeyError: 'jinja2._identifier'
```
