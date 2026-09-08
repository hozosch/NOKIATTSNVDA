#!/usr/bin/env python3
"""Turn an existing generated frontend into an empty model-neutral AOT seed."""

from __future__ import annotations

import argparse
import gzip
import re
from pathlib import Path


def read_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")


def make_seed(source: str, entry: int) -> str:
    dispatch = source.index("dispatch:\n")
    switch = "    switch((uint32_t)reg_pc&~1u){\n"
    start = source.index(switch, dispatch) + len(switch)
    finished = source.index("finished:", start)
    source = source[:start] + "    default: goto yielded;\n    }\n" + source[finished:]
    source, count = re.subn(
        r"    if\(!reg_pc\)reg_pc=UINT64_C\(\d+\);",
        f"    if(!reg_pc)reg_pc=UINT64_C({entry});",
        source,
        count=1,
    )
    if count != 1:
        raise ValueError("generated frontend entry point was not found")
    if re.search(r"(?m)^L_[0-9a-f]{8}:$", source):
        raise ValueError("model-specific labels remained in the AOT seed")
    marker = "static uint8_t *segment(NokiaFrontendMachine*m,uint32_t a,unsigned n) {"
    helpers = r'''static uint64_t nokia_float_add(uint64_t a,uint64_t b,unsigned s){
    if(s==4){float x,y,z;uint32_t u=(uint32_t)a,v=(uint32_t)b,w;memcpy(&x,&u,4);memcpy(&y,&v,4);z=x+y;memcpy(&w,&z,4);return w;}
    if(s==8){double x,y,z;uint64_t w;memcpy(&x,&a,8);memcpy(&y,&b,8);z=x+y;memcpy(&w,&z,8);return w;}return 0;}
static uint64_t nokia_float_sub(uint64_t a,uint64_t b,unsigned s){
    if(s==4){float x,y,z;uint32_t u=(uint32_t)a,v=(uint32_t)b,w;memcpy(&x,&u,4);memcpy(&y,&v,4);z=x-y;memcpy(&w,&z,4);return w;}
    if(s==8){double x,y,z;uint64_t w;memcpy(&x,&a,8);memcpy(&y,&b,8);z=x-y;memcpy(&w,&z,8);return w;}return 0;}
static uint64_t nokia_float_mult(uint64_t a,uint64_t b,unsigned s){
    if(s==4){float x,y,z;uint32_t u=(uint32_t)a,v=(uint32_t)b,w;memcpy(&x,&u,4);memcpy(&y,&v,4);z=x*y;memcpy(&w,&z,4);return w;}
    if(s==8){double x,y,z;uint64_t w;memcpy(&x,&a,8);memcpy(&y,&b,8);z=x*y;memcpy(&w,&z,8);return w;}return 0;}
static uint64_t nokia_float_div(uint64_t a,uint64_t b,unsigned s){
    if(s==4){float x,y,z;uint32_t u=(uint32_t)a,v=(uint32_t)b,w;memcpy(&x,&u,4);memcpy(&y,&v,4);z=x/y;memcpy(&w,&z,4);return w;}
    if(s==8){double x,y,z;uint64_t w;memcpy(&x,&a,8);memcpy(&y,&b,8);z=x/y;memcpy(&w,&z,8);return w;}return 0;}
static uint64_t nokia_float_neg(uint64_t a,unsigned s){
    return s==4?(a^UINT64_C(0x80000000)):(s==8?(a^UINT64_C(0x8000000000000000)):a);}
'''
    if marker not in source:
        raise ValueError("generated frontend memory helper marker was not found")
    source = source.replace(marker, helpers + marker, 1)
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--entry", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        make_seed(read_text(args.source), args.entry),
        encoding="utf-8",
        newline="\n",
    )
    print(f"created empty frontend AOT seed for entry 0x{args.entry:08x}")


if __name__ == "__main__":
    main()
