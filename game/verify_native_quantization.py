"""Check color fidelity through the APK's actual native PNG-to-atlas hook."""

from argparse import ArgumentParser
from io import BytesIO
from math import sqrt
from pathlib import Path
from struct import pack, unpack_from
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from PIL import Image, ImageDraw
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_SP, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_PC,
)

from patch_profile import LIBRARY

BASE, ARENA = 0x10000000, 0x20000000
STACK, BITMAP, SOURCE, ROWS = (ARENA + n * 0x1000 for n in range(1, 5))
SOURCE_PIXELS, DESTINATION = ARENA + 0x10000, ARENA + 0x100000


def verify(apk, preview=None):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type='PT_LOAD'))
    end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(BASE + segment['p_vaddr'], segment.data())
    arm.mem_map(ARENA, 0x200000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    def put(address, *values):
        arm.mem_write(address, pack('<' + 'I' * len(values), *values))

    def convert(pixels, width, height):
        # Exercise the stock Blit call site, its stack ABI, nonzero x/y and
        # unused row padding, as well as the C quantizer it now delegates to.
        stride = width + 8
        sentinel = b'\xfe\xca' * stride * (height + 2)
        arm.mem_write(DESTINATION, sentinel)
        arm.mem_write(SOURCE_PIXELS, bytes(pixels))
        put(ROWS, *(SOURCE_PIXELS + width * 4 * y for y in range(height)))
        put(SOURCE, 0x1401, width, height, 0, SOURCE_PIXELS, ROWS)
        put(BITMAP, 0x8033, stride, height + 2, 0, DESTINATION, 0)
        put(STACK, height, SOURCE, 3, 1, width, height, 0)
        for reg, value in ((UC_ARM_REG_R0, BITMAP), (UC_ARM_REG_R1, 0),
                           (UC_ARM_REG_R2, 0), (UC_ARM_REG_R3, width), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + 0x8D3CD4, BASE + 0x8D3CD8, count=20_000_000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + 0x8D3CD8
        assert arm.reg_read(UC_ARM_REG_SP) == STACK
        result = bytes(arm.mem_read(DESTINATION, len(sentinel)))
        output = bytearray()
        for row in range(height + 2):
            start = row * stride * 2
            if row in (0, height + 1):
                assert result[start:start + stride * 2] == sentinel[start:start + stride * 2]
            else:
                assert result[start:start + 6] == sentinel[start:start + 6]
                edge = start + (width + 3) * 2
                assert result[edge:start + stride * 2] == sentinel[edge:start + stride * 2]
                output.extend(result[start + 6:edge])
        return output

    # 256 constant gray swatches, each covering complete dither periods.
    # Their average decoded color must track *every* input level instead of
    # collapsing ranges of 16 adjacent colors into a single flat block.
    width = height = 256
    pixels = bytearray()
    values = []
    for y in range(height):
        for x in range(width):
            value = ((height - 1 - y) // 16) * 16 + x // 16
            values.append(value)
            pixels.extend((value, value, value, 255))
    packed = convert(pixels, width, height)
    sums, counts = [0] * 256, [0] * 256
    decoded = bytearray()
    for i, value in enumerate(values):
        color, = unpack_from('<H', packed, i * 2)
        r, g, b, a = (17 * ((color >> shift) & 15) for shift in (12, 8, 4, 0))
        assert r == g == b and a == 255  # No new colored noise in grays.
        assert abs(r - value) <= 16
        if value % 17 == 0:
            assert r == value  # Already representable colors remain bit-exact.
        sums[value] += r
        counts[value] += 1
        decoded.extend((r, g, b, a))
    averages = [total / count for total, count in zip(sums, counts)]
    assert max(abs(avg - value) for value, avg in enumerate(averages)) < 0.27
    assert all(b > a for a, b in zip(averages, averages[1:]))
    assert averages[94] - averages[81] > 12  # The former truncation made both 85.
    old_rms = sqrt(sum((((v >> 4) * 17) - v) ** 2 for v in range(256)) / 256)
    rms = sqrt(sum((avg - v) ** 2 for v, avg in enumerate(averages)) / 256)
    assert rms < old_rms / 20

    palette = bytearray()
    for i in range(4096):
        palette.extend(((i & 15) * 17, ((i >> 4) & 15) * 17, ((i >> 8) & 15) * 17, 255))
    palette_result = convert(palette, 64, 64)
    for i in range(4096):
        expected = ((i & 15) << 12) | (((i >> 4) & 15) << 8) | (((i >> 8) & 15) << 4) | 15
        if i == 0xF0F:  # The engine reserves opaque magenta as transparency.
            expected = 0
        assert unpack_from('<H', palette_result, i * 2)[0] == expected

    # Alpha must depend only on alpha, not the dither phase or RGB. Transparent
    # pixels and the engine's magenta key must remain clear without edge noise.
    alpha_pixels = bytearray()
    for y in range(16):
        for a in range(256):
            alpha_pixels.extend((73, 128, 201, a))
    alpha = convert(alpha_pixels, 256, 16)
    for y in range(16):
        for a in range(256):
            color, = unpack_from('<H', alpha, (y * 256 + a) * 2)
            assert (color & 15) == (a + 8) // 17
            if a < 9:
                assert color == 0
    keyed = convert(bytes((255, 0, 255, 255)) * 64, 8, 8)
    assert keyed == bytes(128)
    print(f'RGB block-average RMS error {old_rms:.3f} -> {rms:.3f}; '
          'all 256 gray means ordered, palette exact, alpha stable, keyed pixels clear, padding preserved.')

    if preview:
        # A diagnostic rendering of the measured native output, not a new asset.
        original = Image.frombytes('RGBA', (width, height), bytes(pixels)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        old = bytearray()
        for r, g, b, a in zip(*[iter(pixels)] * 4):
            old.extend(((r >> 4) * 17, (g >> 4) * 17, (b >> 4) * 17, a))
        previous = Image.frombytes('RGBA', (width, height), bytes(old)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        fixed = Image.frombytes('RGBA', (width, height), bytes(decoded)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        canvas = Image.new('RGB', (width * 3, height + 28), '#202124')
        draw = ImageDraw.Draw(canvas)
        for i, (label, tile) in enumerate((('Source (RGBA8888)', original), ('Before: truncation', previous), ('After: RGB dither', fixed))):
            draw.text((i * width + 8, 8), label, fill='white')
            canvas.paste(tile, (i * width, 28))
        Path(preview).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(preview)


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('--preview')
    args = parser.parse_args()
    verify(args.apk, args.preview)
