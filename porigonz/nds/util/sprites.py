# encoding: utf8
"""Handling NDS sprites."""

from collections import namedtuple
from cStringIO import StringIO

from construct import *
from PIL import Image

from porigonz.nds.util import cap_to_bits, word_iterator

# Nintendo color resource; wraps palletes
nclr_struct = Struct('nclr',
    Const(Bytes('magic', 4), 'RLCN'),
    Const(Bytes('bom', 4), '\xff\xfe\x00\x01'),
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('num_sections'),
    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
)

# Palette data
ttlp_struct = Struct('ttlp',
    Const(Bytes('magic', 4), 'TTLP'),
    ULInt32('length'),
    ULInt32('bit_depth'),
    Const(ULInt32('padding'), 0),
    ULInt32('data_length'),  # XXX what?  see docs
    ULInt32('num_colors'),

    # XXX This should use some other field for length but they all seem wrong
    MetaField('data', lambda ctx: 16 * 2),
)

class Palette(object):
    """Represents a DS palette.
    
    After creating a palette, a list of color stored as r, g, b tuples is
    available from the colors property.
    """

    def __init__(self, chunk):
        """Parses a binary chunk as a B5 G5 R5 palette."""
        self.colors = []

        nclr = nclr_struct.parse(chunk)
            
        # XXX this SHOULD have two sections according to format docs.
        # ttlp.data won't leak into a following section, at least
        ttlp = ttlp_struct.parse(nclr.data)

        for palette_word in word_iterator(ttlp.data, 16):
            r = ((palette_word & 0x001f)      ) * 255 // 31
            g = ((palette_word & 0x03e0) >> 5 ) * 255 // 31
            b = ((palette_word & 0x7c00) >> 10) * 255 // 31

            self.colors.append((r, g, b))

    def png(self):
        """Returns a PNG illustrating the colors in this palette."""

        img = Image.new(mode='RGB', size=(len(self.colors), 1), color=None)

        for i, color in enumerate(self.colors):
            img.putpixel((i, 0), color)

        img = img.resize((8 * len(self.colors), 8))

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()


# Nintendo character graphic resource
rgcn_struct = Struct('rgcn',
    Const(Bytes('magic', 4), 'RGCN'),
    Const(Bytes('bom', 4), '\xff\xfe\x00\x01'),
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('num_sections'),
    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
)

# "Character" data
# Most of this seems totally wrong for Pokémon
rahc_struct = Struct('rahc',
    Const(Bytes('magic', 4), 'RAHC'),
    Const(ULInt8('header_length'), 0x20),
    BitStruct('length',
        BitField('length', 24),
    ),
    ULInt16('num_pixels'),
    ULInt16('pixel_size'),
    ULInt32('bit_depth'),
    ULInt64('padding'),
    ULInt32('data_size'),
    ULInt32('unknown1'),
#    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
    MetaField('data', lambda ctx: 6400),  # XXX length is off by a factor of 1024??
)

Size = namedtuple('Size', ['width', 'height'])

class Sprite(object):
    """Represents a DS sprite."""

    @classmethod
    def from_pokemon(cls, chunk):
        """Parses a Pokémon sprite from a chunk.

        This encryption is only used for the Pokémon themselves and trainers.
        Items, berries, the map, the bag, etc. are all regular DS sprites.

        Encryption is an affine cipher, apparently based on the Pokémon PRNG.
        """

        self = cls()

        rgcn = rgcn_struct.parse(chunk)
        rahc = rahc_struct.parse(rgcn.data)

        # XXX make these less constant sometime.
        # XXX and determine which constants to use.
        self.size = Size(width=160, height=80)
        # D/P
        # similarly uses a different add constant for the first block
        add = 0x61a1
        mult = 0xeb65
        # Platinum
        # These actually produce the same sequence as D/P, only backwards.  It
        # appears the mask in D/P started at the end and was generated
        # backwards, but some sprites in Platinum have a non-blank last pixel,
        # so they had to switch it around and use the first pixel (with the
        # same constants) as a seed instead.  I'm always using the first pixel
        # as the seed, so I have inverse constants
        # add = 0x89c3  # appears to be the first dummy block only?
        add = 0x6073
        mult = 0x4e6d

        # Simple mask generator
        def mask_generator():
            key = next(word_iterator(rahc.data[0:2], 16))
            while True:
                yield key
                key = cap_to_bits(key * mult + add, 16)

        # Unmask the sprite data
        mask = mask_generator()
        self.pixels = [[0] * self.size.height for _ in range(self.size.width)]
        for i, word in enumerate(word_iterator(rahc.data, 16)):
            unmasked = word ^ next(mask)

            # This is 16 bits, and there are four bits per pixel, so we have
            # four pixels
            x, y = self.get_pos(i * 4)
            for _ in range(4):
                self.pixels[x][y] = unmasked & 0x0f
                unmasked >>= 4
                x += 1

        return self

    def get_pos(self, idx):
        """Given a linearized index, returns the x, y coordinates within the
        image.
        """
        return idx % self.size.width, idx // self.size.width

    def fake_color(self, idx):
        """Given a palette index, returns a unique fake color to represent it.
        """
        sat = idx * 255 / 15
        return sat, sat, sat

    def png(self):
        """Returns this sprite as a PNG.  Colors are merely shades of gray."""
        img = Image.new(mode='RGB', size=self.size, color=None)

        for x in xrange(self.size.width):
            for y in xrange(self.size.height):
                img.putpixel((x, y), self.fake_color(self.pixels[x][y]))

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()
