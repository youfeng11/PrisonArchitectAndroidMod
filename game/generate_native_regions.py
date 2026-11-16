from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import hashlib
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
import math,struct
root = Path(__file__).resolve().parents[1]
parser = ArgumentParser(description="Read the sprite UV rectangles from Prison Architect Mobile 2.0.9.")
parser.add_argument("--apk", type=Path, default=root / "com.paradoxplaza.prisonarchitect.apk")
parser.add_argument("--obb", type=Path, default=root / "com.paradoxplaza.prisonarchitect" / "main.49.com.paradoxplaza.prisonarchitect.obb")
parser.add_argument("--output", type=Path, default=root / "fixtures/native/native-regions.tsv")
args = parser.parse_args()
with ZipFile(args.apk) as apk:
 native = apk.read("lib/armeabi-v7a/libmain.so")
assert hashlib.sha256(native).hexdigest() == "2fcf85dfb73f61188e1bc8c811ab76f74659f7a317b6f25ed05cc0a919aea3e3", "Unexpected renderer build"
start,end=0x8cb358,0x8cb5d8
hooks={}
with BytesIO(native) as f:
 elf=ELFFile(f)
 text=elf.get_section_by_name('.text')
 code=text.data()[start-text['sh_addr']:end-text['sh_addr']]
 got={0x3cbac8+8+11534336+77824+0x4cc:0x3cbac8,0x3b0a8c+8+11534336+151552+0x4f4:0x3b0a8c}
 for sec in elf.iter_sections():
  if sec.name=='.rel.plt':
   syms=elf.get_section(sec['sh_link'])
   for rel in sec.iter_relocations():
    if rel['r_offset'] in got: hooks[got[rel['r_offset']]]=syms.get_symbol(rel['r_info_sym']).name
print('Native math imports:',hooks)
assert set(hooks.values())=={'acosf','fmodf'}
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for addr,length in [(start&~0xfff,0x1000),(0x100000,0x2000),(0x200000,0x2000),(0x3cb000,0x1000),(0x3b0000,0x1000)]:
 u.mem_map(addr,length)
u.mem_write(start,code)
u.reg_write(UC_ARM_REG_C1_C0_2,0xf<<20)
u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
def math_call(uc,address,size,user):
 name=hooks.get(address)
 if not name:return
 a=struct.unpack('<f',struct.pack('<I',uc.reg_read(UC_ARM_REG_R0)))[0]
 if name=='acosf':
  val=math.acos(max(-1,min(1,a)))
 else:
  b=struct.unpack('<f',struct.pack('<I',uc.reg_read(UC_ARM_REG_R1)))[0]
  val=math.fmod(a,b)
 uc.reg_write(UC_ARM_REG_R0,struct.unpack('<I',struct.pack('<f',val))[0])
 uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,math_call)
def crop(x,y,w,h,t,top,dx,dy):
 u.mem_write(0x100000,struct.pack('<3I5I?',0,0,0,x,y,w,h,t,top))
 u.mem_write(0x100080,struct.pack('<2f',dx,dy))
 u.mem_write(0x100100,bytes(32))
 u.mem_write(0x201000,struct.pack('<5I',0x100108,0x10010c,0x100110,0x100114,0x100118))
 for reg,value in [(UC_ARM_REG_R0,0x100000),(UC_ARM_REG_R1,0x100080),(UC_ARM_REG_R2,0x100100),(UC_ARM_REG_R3,0x100104),(UC_ARM_REG_SP,0x201000),(UC_ARM_REG_LR,0x200000)]:
  u.reg_write(reg,value)
 u.emu_start(start,0x200000,count=500)
 return struct.unpack('<7i',u.mem_read(0x100100,28))[1:5]
for name,x,y,w,h,t,top in [
 ('RiotGuard',48,124,2,2,1,False),('CctvMonitor',23,25,6,3,1,False),('Table',11,19,8,3,2,True),
 ('GuardTowerFull',52,6,4,8,3,False),('Light',35,10,2,2,4,False),('Cctv',30,28,1,1,6,False),('Door',16,0,2,2,6,False),
]:
 result=[]
 for dx,dy in [(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1),(1,0),(1,1)]:
  norm=math.hypot(dx,dy)
  result.append(crop(x,y,w,h,t,top,dx/norm,dy/norm))
 print(name,result)

import re
with ZipFile(args.obb) as z:
 bank=z.read('data/objects.spritebank').decode().split('BEGIN Markers')[0]
 rows=re.findall(r'BEGIN "\[i (\d+)\]"\s+Name ("[^"]+"|\S+)\s+x (\d+)\s+y (\d+)\s+w (\d+)\s+h (\d+)\s+RotateType (\d+)\s+TopAligned (true|false)',bank)
 assert len(rows) == int(re.search(r'\bSize\s+(\d+)', bank)[1])
 args.output.parent.mkdir(parents=True, exist_ok=True)
 with args.output.open('w',encoding='utf-8') as out:
  for id,name,x,y,w,h,t,top in rows:
   regions=set()
   for dx,dy in [(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1),(1,0),(1,1)]:
    norm=math.hypot(dx,dy)
    region=crop(*map(int,(x,y,w,h,t)),top=='true',dx/norm,dy/norm)
    regions.add(tuple(v*32 for v in region))
   out.write(id+'\t'+name.strip('"')+'\t'+';'.join(','.join(map(str,r)) for r in sorted(regions))+'\n')
print('Captured the native rectangles for all',len(rows),'object sprites.')
