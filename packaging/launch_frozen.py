"""Frozen launcher for Clear Silence. App code stays in the ordinary repo modules."""
import runpy
import sys

if '--self-test' in sys.argv:
    import app  # ensures ui.html is bundled and readable
    import audio
    import webview
    assert app.APP_VERSION == '0.3.0'
    assert app.HTML.startswith('<!doctype html>')
    assert callable(audio.WavFile)
    print('Clear Silence frozen application import check OK')
    raise SystemExit(0)

runpy.run_module('app', run_name='__main__')
