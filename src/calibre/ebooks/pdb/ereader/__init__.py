__license__   = 'GPL v3'
__copyright__ = '2009, John Schember <john@nachtimwald.com>'
__docformat__ = 'restructuredtext en'

import os


class EreaderError(Exception):
    pass


def image_name(name, taken_names=()):
    name = os.path.basename(name)

    if len(name) > 32:
        cut = len(name) - 32
        names = name[:10]
        namee = name[10+cut:]
        name = '{}{}.png'.format(names, namee)

    i = 0
    base_name, ext = os.path.splitext(name)
    while name in taken_names:
        i += 1
        name = '{}{}{}'.format(base_name, i, ext)

    return name.ljust(32, '\x00')[:32]
