# -*- mode: python ; coding: utf-8 -*-

import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

a = Analysis(
    ['openchronomorphviewer.py'],
    pathex=[],
    binaries=[],
    datas=[
		('ui/graphics/*.png', 'ui/graphics'),
		('ui/graphics/*.ico', 'ui/graphics'),
	],
    hiddenimports=['vtkmodules', 'vtkmodules.all', 'vtkmodules.qt.QVTKRenderWindowInteractor', 'vtkmodules.util', 'vtkmodules.util.numpy_support', 'vtkmodules.numpy_interface', 'vtkmodules.numpy_interface.dataset_adapter'],
	excludes=['IPython', 'PIL', 'PyQt5.uic', 'PyQt6', 'Pythonwin', 'abc', 'alabaster', 'asyncio', 'babel', 'bdb', 'calendar', 'certifi', 'cffi', 'charset_normalizer', 'cmd', 'code', 'codeop', 'contourpy', 'cryptography', 'csv', 'decimal', 'distutils', 'doctest', 'docutils', 'email', 'fractions', 'ftplib', 'getopt', 'getpass', 'gettext', 'gi', 'html', 'http', 'imp', 'jinja', 'jinja2', 'markupsafe', 'matplotlib', 'mimetypes', 'netrc', 'nturl2path', 'packaging', 'pandas', 'pdb', 'pkg_resources', 'pprint', 'py_compile', 'pydoc', 'pydoc_data', 'pygments', 'pytest', 'pytz', 'pywin32', 'pywin32_system32', 'quopri', 'runpy', 'setuptools', 'six', 'socketserver', 'sphinx', 'ssl', 'statistics', 'stringprep', 'struct', 'sysconfig', 'tarfile', 'tcl', 'threadpoolctl', 'tkinter', 'tomli', 'tornado', 'tracemalloc', 'tty', 'tzdata', 'unittest', 'win32', 'win32com', 'xml', 'xmlrpc', 'yaml', 'zipp'],
	# Critical modules must not be excluded: ['multiprocessing', 'typing_extensions', 'difflib', 'pickle', 'heapq']
	# Required by tifffile: ['concurrent', 'queue']
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OCMV',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['ui\\graphics\\icon_window.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='openchronomorphviewer',
)
