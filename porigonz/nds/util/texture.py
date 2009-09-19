from construct import *
from construct.lib import int_to_bin, bin_to_int
from PIL import Image
from cStringIO import StringIO
from collections import namedtuple
from itertools import izip as zip
from math import sqrt, ceil

from porigonz.nds.util import word_iterator

#http://tahaxan.arcnor.com/forums/index.php?action=printpage%3Btopic=34.0
#http://tahaxan.arcnor.com/forums/index.php?topic=65.0

bpp = [0, 8, 2, 4, 4, 8, 2, 8, 16]

# XXX call this Div8 instead?
class TimesEight(Adapter):
    """these structs seem to contain a lot of integers that are off by a factor of eight. this class corrects that"""
    def _encode(self, obj, ctx):
        return obj / 8
    def _decode(self, obj, ctx):
        return obj * 8

#for little-endian bitstruct
def Swapped(subcon):
    return Buffered(subcon,
        encoder = (lambda buf: buf[::-1]),
        decoder = (lambda buf: buf[::-1]),
        resizer = (lambda length: length)
    )

block_header = Struct('header',
    Padding(1),
    ULInt8('count'),
    ULInt16('block_length'),
    #Probe(),
    Const(ULInt16(None), 8), # bpp?
    ULInt16('header_length'),
    Const(ULInt32(None), 0x17f),

    Array(lambda ctx: ctx.count, ULInt32('unknown0')),
)

name_array = Array(lambda ctx: ctx.header.count, String('names', 16, padchar="\x00"))

texture_def_struct = Struct('texture',
    block_header,

    Const(ULInt16(None), 8),
    ULInt16('length'),
    Array(lambda ctx: ctx.header.count, Struct('info',
        TimesEight(ULInt16('offset')),
        Embed(Swapped(BitStruct('',
            #starting with the MSB
            Padding(2),
            Flag('color0'), #indcates that the first color is transparent
            Bits('format', 3),
            Bits('height', 3),
            Bits('width', 3),
            Padding(4),
            #LSB
        ))),
        Padding(4), #unknown

        Value('height', lambda ctx: 8 << ctx.height),
        Value('width', lambda ctx: 8 << ctx.width),
        Value('size', lambda ctx: ctx.width * ctx.height * bpp[ctx.format] // 8),

        OnDemandPointer(
            lambda ctx: ctx._._.start + ctx._._.texture_data_ptr + ctx.offset,
            MetaField('data', lambda ctx: ctx.size)
        ),
    )),
    #Array(lambda ctx: ctx.header.count,),

    name_array
)

palette_def_struct = Struct('palette',
    block_header,

    Const(ULInt16(None), 4),
    ULInt16('length'),
    Array(lambda ctx: ctx.header.count, TimesEight(ULInt32('offsets'))),

    #can't figure out the palette length without knowing the bpp of the
    #texture, so just grab the data. it's not very big.
    Pointer(
        lambda ctx: ctx._.start + ctx._.palette_data_ptr,
        MetaField('data', lambda ctx: ctx._.length - ctx._.palette_data_ptr)
    ),

    name_array
)

tex0_struct = Struct('tex0',
    Anchor("start"),

    Const(Bytes('magic', 4), 'TEX0'),
    ULInt32('length'),
    Padding(4), #Const(ULInt32('padding'), 0),
    TimesEight(ULInt16('texture_data_length')),
    Const(ULInt16('section_length'), 0x3c), #texture_def_ptr?
    Padding(4), #Const(ULInt32('padding'), 0),
    ULInt32('texture_data_ptr'),
    Padding(4), #Const(ULInt32('padding'), 0),

    #these pertain to texture format #5
    TimesEight(ULInt16('sp_texture_size')),
    Const(ULInt16(None), 0x3c),
    Padding(4),
    ULInt32('sp_texture_ptr'),
    ULInt32('sp_data_ptr'),

    Padding(4), #Const(ULInt32('padding'), 0),
    TimesEight(ULInt16('palette_data_size')),
    Padding(2),
    ULInt32('palette_def_ptr'),
    ULInt32('palette_data_ptr'),
    
    texture_def_struct,
    palette_def_struct,

    #OnDemandPointer(lambda ctx: ctx.texture_data_ptr, )
)

btx0_struct = Struct('btx0',
    Const(Bytes('magic', 4), 'BTX0'),
    Const(Bytes('bom', 2), '\xff\xfe'),
    Bytes('something', 2),
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('count'),

    Array(lambda ctx: ctx.count, Struct('blocks',
        ULInt32('offset'),
        OnDemandPointer(lambda ctx: ctx.offset, tex0_struct),
    )),
)

__metaclass__ = type

Size = namedtuple('Size', 'width height')

class NSBTX:
    def __init__(self, chunk):
       self.btx0 = btx0_struct.parse(chunk)
       self.blocks = [TextureBlock(b.tex0.value) for b in self.btx0.blocks]

class TextureBlock:
    def __init__(self, tex0):
        self.tex0 = tex0
        
        self.texture_count = tex0.texture.header.count
        self.palette_count = tex0.palette.header.count

        self.textures = [Texture(t, t.data) for t in tex0.texture.info]
        self.palettes = [Palette(tex0.palette.data[offset:])
                         for offset in tex0.palette.offsets]

        for t, name in zip(self.textures, tex0.texture.names):
            t.name = name

        if '.' in name:
            self.name = name.split('.', 1)[0]

    def get_texture(self, value):
        if hasattr(value, '__index__'):
            value = value.__index__()
        else:
            #filename
            value = self.tex0.texture.names.index(value)
        return Texture(self.tex0.texture.info[value],
                       self.tex0.texture.info[value].data)

    __getitem__ = get_texture

    def image(self, palette=None):
        if self.texture_count <= 4:
            width = self.texture_count
            height = 1
        else:
            # pick the greatest width such that width < height
            # and height is a multiple of 4
            height = 4
            width = self.texture_count // height
            while self.texture_count % 4 == 0 and 4 < width:
                height += 4
                width = self.texture_count // height

        #i'm assuming that all the textures are the same size
        size = self.textures[0].size
        #flag = False
        #for t in self.textures:
        #    if t.size != size:
        #        print size
        #        flag = True
        #if flag:
        #    return None
        
        textures = self.textures[:]
        if '.' in textures[0].name:
            try:
                textures.sort(key=(lambda x: int(x.name.split('.')[1])))
            except ValueError:
                pass

        if palette is None:
            palette = self.palettes[0]

        bigimg = Image.new(mode="RGBA", size=(size.width*width, size.height*height))

        for t, (x, y) in zip(textures, 
                             ((x, y) for y in xrange(height)
                                       for x in xrange(width))):
            point = (x * size.width, y * size.height)
            img = t.image(palette)
            bigimg.paste(img, point)

        return bigimg


    def png(self, palette=None):
        img = self.image(palette)

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()


    def __str__(self):
        return self.png()
        
class Texture:
    def __init__(self, info, data):
        self.info = info
        self.data = data
        self.format = info.format
        self.size = Size(info.width, info.height)
        self._pixels = None

    @property
    def pixels(self):
        if self._pixels is not None:
            return self._pixels
        # [width][height]
        self._pixels = [[0] * self.size.height for _ in range(self.size.width)]
        pixdata = self.data.value
        format = self.format
        if format == 3:
            # 16-color palette
            it = word_iterator(pixdata, 4)
            for y in range(self.info.height):
                for x in range(self.info.width):
                    pix = it.next()
                    self._pixels[x][y] = pix
        elif format == 5:
            raise NotImplementedError
        else:
            raise NotImplementedError

        return self._pixels


    def image(self, palette=None):
        img = Image.new(mode='RGBA', size=self.size, color=None)

        if palette:
            if palette.format is None:
                palette.format = self.format
            colors = palette.colors
        else:
            colors = [(sat, sat, sat) for sat in ((15 - _) * 255 / 15 for _ in range(16))]

        colors = [color + (255,) for color in colors]
        if self.info.color0:
            colors[0] = colors[0][:3] + (0,)

        data = img.load()
        for x in xrange(self.info.width):
            for y in xrange(self.info.height):
                data[x, y] = colors[self.pixels[x][y]]

        return img

    def png(self, palette=None):
        img = self.image(palette)

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()

    def __str__(self):
        return self.png()
        
# http://nocash.emubase.de/gbatek.htm#ds3dtextureformats
class Palette:
    def __init__(self, data, format=None):
        self.format = format
        self.data = data

        self.colors = []


    def set_format(self, format):
        if format is None:
            self._format = None
        elif format == self._format:
            pass
        elif format == 5:
            raise NotImplementedError
        elif format == 7:
            #direct color texture -- no palette
            raise ValueError
        else:
            self._format = format
            size = 1 << bpp[format]
            for _, w in zip(range(size), word_iterator(self.data, 16)):
                r = (w & 0x1f) * 255 // 31
                g = ((w >> 5) & 0x1f) * 255 // 31
                b = ((w >> 10) & 0x1f) * 255 // 31
                self.colors.append((r, g, b))

    def get_format(self):
        return self._format

    format = property(get_format, set_format)
            
    def png(self):
        """Returns a PNG illustrating the colors in this palette."""

        img = Image.new(mode='RGB', size=(len(self.colors), 1), color=None)

        for i, color in enumerate(self.colors):
            img.putpixel((i, 0), color)

        img = img.resize((8 * len(self.colors), 8))

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()

    def __str__(self):
        """Returns this palette as a PNG."""
        return self.png()

