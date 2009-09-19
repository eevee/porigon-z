from construct import *
from construct.lib import int_to_bin, bin_to_int
from PIL import Image
from cStringIO import StringIO

from porigonz.nds.util import word_iterator

#http://tahaxan.arcnor.com/forums/index.php?action=printpage%3Btopic=34.0
#http://tahaxan.arcnor.com/forums/index.php?topic=65.0

bpp = [0, 8, 2, 4, 4, 8, 2, 8, 16]

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

filenames = Array(lambda ctx: ctx.header.count, String('names', 16, padchar="\x00"))

texture_struct = Struct('texture',
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

    filenames
)

palette_struct = Struct('palette',
    block_header,

    Const(ULInt16(None), 4),
    ULInt16('length'),
    Array(lambda ctx: ctx.header.count, TimesEight(ULInt32('offsets'))),

    Pointer(
        #lambda ctx: ctx._.start + ctx._.palette_data_ptr + ctx.offset,
        lambda ctx: ctx._.start + ctx._.palette_data_ptr,
        MetaField('data', lambda ctx: ctx._.length - ctx._.palette_data_ptr)
    ),

    filenames
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
    
    texture_struct,
    palette_struct,

    #OnDemandPointer(lambda ctx: ctx.texture_data_ptr, )
)

btx0_struct = Struct('btx0',
    Const(Bytes('magic', 4), 'BTX0'),
    Const(Bytes('bom', 2), '\xff\xfe'),
    Bytes('something', 2),
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('count'),

    Array(lambda ctx: ctx.count, ULInt32('block_offset')),

    tex0_struct,
)

__metaclass__ = type

#class NSBTX:
#    def __init__(self, chunk):
#       btx = btx0_struct.parse(chunk)
#       TextureList(self, btx.tex0)

class TextureList:
    def __init__(self, chunk):
        if hasattr(chunk, 'read'):
            btx0 = btx0_struct.parse_stream(chunk)
        else:
            btx0 = btx0_struct.parse(chunk)
        
        self.btx0 = btx0 # i'm not sure if i even need to keep this around
        self.tex0 = btx0.tex0
        
        self.texture_count = self.tex0.texture.header.count
        self.palette_count = self.tex0.palette.header.count

    def get_texture(self, value):
        if hasattr(value, '__index__'):
            value = value.__index__()
        else:
            #filename
            value = self.tex0.texture.filename.index(value)
        return Texture(self.tex0.texture.info[value],
                       self.tex0.texture.info[value].data)

    __getitem__ = get_texture

    def png(self, tex, pal=None):
        """make a png from the texture (and palette) of the given indicies"""
        tex = self[tex]
        palette = Palette(tex.format,
                          self.tex0.palette.data[self.tex0.palette.offsets[pal]:])
        return tex.png(palette)
        
class Texture:
    def __init__(self, info, data):
        self.info = info
        self.data = data
        self.format = format = info.format
        self.size = (info.width, info.height)

        # [width][height]
        self.pixels = [[0] * self.info.height for _ in range(self.info.width)]
        pixdata = data.value
        if format == 3:
            # 16-color palette
            it = word_iterator(pixdata, 4)
            for x in range(self.info.width):
                for y in range(self.info.height):
                    pix = it.next()
                    self.pixels[x][y] = pix
        elif format == 5:
            raise NotImplementedError
        else:
            raise NotImplementedError

    def png(self, palette = None):
        img = Image.new(mode='RGBA', size=self.size, color=None)

        if palette:
            colors = palette.colors
        else:
            colors = [(sat, sat, sat) for sat in ((15 - _) * 255 / 15 for _ in range(16))]

        colors = [color + (255,) for color in colors]
        if self.info.color0:
            colors[0] = colors[0][:3] + (0,)

        data = img.load()
        for x in xrange(self.info.width):
            for y in xrange(self.info.height):
                data[x, y] = colors[ self.pixels[x][y] ]

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()
        
# http://nocash.emubase.de/gbatek.htm#ds3dtextureformats
class Palette:
    def __init__(self, format, data):
        self.format = format
        self.data = data

        self.colors = []

        if format == 5:
            raise NotImplementedError
        
        # XXX hardcoding sucks
        size = 16
        for _, w in zip(range(size), word_iterator(data, 16)):
            r = (w & 0x1f) * 255 // 31
            g = ((w >> 5) & 0x1f) * 255 // 31
            b = ((w >> 10) & 0x1f) * 255 // 31
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

    def __str__(self):
        """Returns this palette as a PNG."""
        return self.png()

        
if __name__ == '__main__':
    f = open("/home/andrew/heartgold.nds:data/a/0/8/1/827", "rb")
    T = TextureList(f)
    for t in range(8):
        for p in range(2):
            out = open("/home/andrew/scrap/btx0/827-%d-%d.png" % (t, p), "wb")
            out.write(T.png(t, p))
            out.close()
    #p = t.png(1,1)
