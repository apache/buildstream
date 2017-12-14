# FIXME: having to hardcode all the names that click-man will generate is
# fragile and annoying

manpages = [
  'bst.1',
  'bst-artifact-receive.1',
  'bst-build.1',
  'bst-checkout.1',
  'bst-fetch.1',
  'bst-pull.1',
  'bst-push.1',
  'bst-shell.1',
  'bst-show.1',
  'bst-source-bundle.1',
  'bst-track.1',
  'bst-workspace.1',
  'bst-workspace-close.1',
  'bst-workspace-list.1',
  'bst-workspace-open.1',
  'bst-workspace-reset.1',
]

click_man_wrapper = join_paths(meson.current_source_dir(), 'click-man-wrapper')

custom_target('manpages',
  command: [python, click_man_wrapper, '@OUTDIR@'],
  output: manpages,
  install: true,
  install_dir: get_option('mandir'),
)
