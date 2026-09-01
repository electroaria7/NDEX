# Third-Party Notices

NDEX Frame (and the NDEX portable release) bundles the following third-party
components. Versions below are the exact packages resolved by the build
environment used to package this release.

## PySide6 6.11.2

- Package: `PySide6==6.11.2`
- License: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (also available under Qt commercial terms)
- Project: https://pyside.org
- Documentation / licenses: https://doc.qt.io/qtforpython-6/licenses.html
- GNU LGPL v3: https://www.gnu.org/licenses/lgpl-3.0.html
- GNU GPL v2: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
- GNU GPL v3: https://www.gnu.org/licenses/gpl-3.0.html
- Qt commercial terms: https://www.qt.io/terms-conditions

PySide6 is the official Qt for Python binding. This distribution uses the
LGPL-licensed Qt for Python wheels from PyPI.

The installed wheel ships this commercial-license notice:

```
Licensees holding valid commercial Qt licenses may use this software in
accordance with the the terms contained in a written agreement between
you and The Qt Company. Alternatively, the terms and conditions that were
accepted by the licensee when buying and/or downloading the
software do apply.

For the latest licensing terms and conditions, see https://www.qt.io/terms-conditions.
For further information use the contact form at https://www.qt.io/contact-us.
```

## Qt 6.11.2

- Runtime version reported by `PySide6.QtCore.qVersion()`: **6.11.2**
- License: LGPL-3.0 / GPL-2.0 / GPL-3.0 / Qt commercial
- Licensing overview: https://doc.qt.io/qt-6/licensing.html
- GNU LGPL v3: https://www.gnu.org/licenses/lgpl-3.0.html
- Source: https://code.qt.io/cgit/qt/qtbase.git/

Qt libraries are redistributed as part of the PySide6 wheels collected into
`NDEX_Frame.exe`. Corresponding Qt source is available from the Qt project
under the licenses above.

## shiboken6 6.11.2

- Package: `shiboken6==6.11.2`
- License: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (also available under Qt commercial terms)
- Project: https://pyside.org
- Documentation / licenses: https://doc.qt.io/qtforpython-6/licenses.html
- GNU LGPL v3: https://www.gnu.org/licenses/lgpl-3.0.html

shiboken6 is the Qt for Python binding generator / runtime helper and is
required by PySide6.

## Pillow 11.3.0

- Package: `pillow==11.3.0` (`PIL`)
- License: MIT-CMU
- Project: https://python-pillow.github.io
- Full wheel license (including bundled codec notices):
  https://github.com/python-pillow/Pillow/blob/11.3.0/LICENSE

Pillow (the friendly PIL fork) is licensed under the open source MIT-CMU License:

```
The Python Imaging Library (PIL) is

    Copyright © 1997-2011 by Secret Labs AB
    Copyright © 1995-2011 by Fredrik Lundh and contributors

Pillow is the friendly PIL fork. It is

    Copyright © 2010 by Jeffrey A. Clark and contributors

Like PIL, Pillow is licensed under the open source MIT-CMU License:

By obtaining, using, and/or copying this software and associated
documentation, you agree that you have read, understood, and will comply
with the following terms and conditions:

Permission to use, copy, modify and distribute this software and its
documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appears in all copies, and that
both that copyright notice and this permission notice appear in supporting
documentation, and that the name of Secret Labs AB or the author not be
used in advertising or publicity pertaining to distribution of the software
without specific, written prior permission.

SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.
IN NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR ANY SPECIAL,
INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```

The Pillow 11.3.0 wheel LICENSE file also includes notices for bundled
third-party codecs (brotli, freetype, harfbuzz, libjpeg-turbo, libpng,
openjpeg, zlib, and others). See the URL above for that complete text.
