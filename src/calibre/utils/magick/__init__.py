#!/usr/bin/env python


__license__   = 'GPL v3'
__copyright__ = '2010, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

from calibre.utils.magick.legacy import Image, PixelWand
from polyglot.builtins import unicode_type

if False:
    PixelWand


def create_canvas(width, height, bgcolor='#ffffff'):
    canvas = Image()
    canvas.create_canvas(int(width), int(height), unicode_type(bgcolor))
    return canvas
