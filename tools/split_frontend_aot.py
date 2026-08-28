#!/usr/bin/env python3
"""Split the generated frontend dispatcher into ARM64-linker-sized functions."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


CHUNK_SIZE = 384
EXECUTIVE = {0x8019DB50, 0x8019DB70, 0x8019DB88}


def route(line: str, local: set[int]) -> str:
    indent = line[:len(line) - len(line.lstrip())]
    statement = line.strip()
    conditional = re.fullmatch(r"if \((.*)\) goto L_([0-9a-f]{8});", statement)
    if not conditional:
        conditional = re.fullmatch(
            r"if \((.*)\) \{ goto L_([0-9a-f]{8}); \}", statement)
    if conditional:
        address = int(conditional.group(2), 16)
        if address not in local:
            return (f"{indent}if ({conditional.group(1)}) {{ reg_pc=UINT64_C({address}); "
                    "return NOKIA_FRONTEND_CONTINUE; }")
        return line
    direct = re.fullmatch(r"goto L_([0-9a-f]{8});", statement)
    if direct:
        address = int(direct.group(1), 16)
        if address not in local:
            return (f"{indent}reg_pc=UINT64_C({address}); "
                    "return NOKIA_FRONTEND_CONTINUE;")
        return line
    return (line.replace("goto dispatch;", "return NOKIA_FRONTEND_CONTINUE;")
                .replace("goto unsupported;", "return NOKIA_FRONTEND_UNSUPPORTED;"))


def split_source(source: str) -> str:
    signature = "NOKIA_EXPORT int nokia_frontend_aot("
    function_at = source.index(signature)
    prefix = source[:function_at]
    body = source[function_at:]
    first_label = re.search(r"(?m)^L_[0-9a-f]{8}:$", body)
    finished = re.search(r"(?m)^finished:$", body)
    if not first_label or not finished or finished.start() <= first_label.start():
        raise ValueError("generated frontend layout was not recognised")

    prologue = body[:first_label.start()]
    variable_names = re.findall(r"(?m)^    uint64_t ([A-Za-z0-9_]+)=0;$", prologue)
    if not variable_names:
        raise ValueError("frontend state variables were not found")
    label_text = body[first_label.start():finished.start()]
    matches = list(re.finditer(r"(?m)^L_([0-9a-f]{8}):$", label_text))
    blocks: dict[int, list[str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(label_text)
        blocks[int(match.group(1), 16)] = label_text[match.start():end].rstrip().splitlines()

    # PrimeSynthesisL can return through 0x801a0684 into this two-instruction
    # ARM byte-copy gap.  It was absent from the original trace, causing one
    # AOT->Unicorn yield per copied byte.  The ROM bytes decode as:
    #   e4d1c001  LDRB r12,[r1],#1
    #   e4c3c001  STRB r12,[r3],#1
    # Keep the tiny loop native so r1/r3/r12 remain in one state model.
    blocks.setdefault(0x801A0688, [
        "L_801a0688:",
        "    nokia_frontend_last_pc=0x801a0688u;",
        "    reg_r12 = ((uint64_t)(nokia_mem_load(&machine, (reg_r1 & UINT64_C(0xffffffff)), 1))) & UINT64_C(0xffffffff);",
        "    reg_r1 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) + UINT64_C(1))) & UINT64_C(0xffffffff);",
        "    goto L_801a068c;",
    ])
    blocks.setdefault(0x801A068C, [
        "L_801a068c:",
        "    nokia_frontend_last_pc=0x801a068cu;",
        "    if (!nokia_mem_store(&machine, (reg_r3 & UINT64_C(0xffffffff)), (reg_r12 & UINT64_C(0xff)), 1)) goto unsupported;",
        "    reg_r3 = ((uint64_t)((reg_r3 & UINT64_C(0xffffffff)) + UINT64_C(1))) & UINT64_C(0xffffffff);",
        "    goto L_801a0690;",
    ])

    addresses = sorted(set(blocks) - EXECUTIVE)
    resume_addresses = sorted({int(value) & ~1 for value in
                               re.findall(r"reg_lr=UINT64_C\((\d+)\)",
                                          label_text)})
    chunks = [addresses[index:index + CHUNK_SIZE]
              for index in range(0, len(addresses), CHUNK_SIZE)]
    old_store = (
        "static int nokia_mem_store(NokiaFrontendMachine*m,uint64_t address,uint64_t value,unsigned size) "
        "{ uint8_t*p=segment(m,(uint32_t)address,size);if(!p){if(!m->bad_address)m->bad_address=(uint32_t)address;"
        "return 0;}memcpy(p,&value,size);return 1; }")
    new_store = (
        "static uint32_t nokia_frontend_dirty_mask;\n"
        "static uint32_t nokia_dirty_segment(uint32_t a){"
        "if(a>=0x50000000u&&a<0x50100000u)return 1u;"
        "if(a>=0x51000000u&&a<0x51001000u)return 2u;"
        "if(a>=0x52000000u&&a<0x52010000u)return 4u;"
        "if(a>=0x53000000u&&a<0x53800000u)return 8u;"
        "if(a>=0x60000000u&&a<0x60100000u)return 16u;return 0u;}\n"
        "static int nokia_mem_store(NokiaFrontendMachine*m,uint64_t address,uint64_t value,unsigned size) "
        "{ uint32_t a=(uint32_t)address;uint8_t*p=segment(m,a,size);if(!p){if(!m->bad_address)m->bad_address=a;"
        "return 0;}nokia_frontend_dirty_mask|=nokia_dirty_segment(a);memcpy(p,&value,size);return 1; }\n"
        "NOKIA_EXPORT uint32_t nokia_frontend_dirty_mask_value(void){return nokia_frontend_dirty_mask;}")
    if old_store not in prefix:
        raise ValueError("generated frontend memory-store helper was not recognised")
    prefix = prefix.replace(old_store, new_store)

    # Nokia's first observer-vtable entry (0x52000224) supplies one of the
    # bundled srsf_<type>_<id>.bin resources. Keep that callback inside the AOT
    # state model: crossing into Unicorn here used to account for three yields
    # per PrimeSynthesisL call. The registry owns the bytes; the frontend host
    # allocator owns the guest-visible copy.
    config_helper = """
extern int nokia_find_config_blob(uint32_t type,uint32_t id,
                                  const uint8_t **data,uint32_t *size);
static uint32_t nokia_frontend_config_blob(NokiaFrontendMachine*m,
 const NokiaFrontendHost*host,uint32_t type,uint32_t id,uint32_t start,uint32_t end){
    const uint8_t*data=NULL;uint32_t size=0,offset=0,count,address;uint8_t*p;
    if(!host||!host->alloc||!nokia_find_config_blob(type,id,&data,&size))return 0;
    if(end&&end>start){offset=start<size?start:size;end=end<size?end:size;count=end>offset?end-offset:0;}
    else{offset=0;count=size;}
    address=host->alloc(host->context,count+8u);if(!address)return 0;
    p=segment(m,address,count+8u);if(!p)return 0;
    nokia_frontend_dirty_mask|=nokia_dirty_segment(address);
    memcpy(p,&count,4);if(count)memcpy(p+4,data+offset,count);return address;
}
"""

    out = [prefix.rstrip(), config_helper.rstrip(), "", "typedef struct {"]
    out.extend(f"    uint64_t {name};" for name in variable_names)
    out.extend(["} NokiaFrontendState;",
                "enum { NOKIA_FRONTEND_UNSUPPORTED=0, NOKIA_FRONTEND_YIELDED=2, NOKIA_FRONTEND_CONTINUE=3 };"])
    out.extend(f"#define {name} (state->{name})" for name in variable_names)
    out.append("#define machine (*machine_ptr)")

    for chunk_index, chunk in enumerate(chunks):
        local = set(chunk)
        out.extend(["",
                    f"static int nokia_frontend_chunk_{chunk_index}(NokiaFrontendState*state,",
                    " NokiaFrontendMachine*machine_ptr,const NokiaFrontendHost*host){",
                    "    switch((uint32_t)reg_pc&~1u){"])
        out.extend(f"    case 0x{address:08x}u: goto L_{address:08x};"
                   for address in chunk)
        out.extend(["    default: return NOKIA_FRONTEND_YIELDED;", "    }"])
        for address in chunk:
            out.extend(route(line, local) for line in blocks[address])
        out.append("}")

    out.extend(["",
                "typedef int (*NokiaFrontendChunk)(NokiaFrontendState*,NokiaFrontendMachine*,const NokiaFrontendHost*);",
                "static NokiaFrontendChunk nokia_frontend_chunks[]={"])
    out.extend(f"    nokia_frontend_chunk_{index}," for index in range(len(chunks)))
    out.extend(["};", "static const uint32_t nokia_frontend_chunk_limits[]={"])
    out.extend(f"    0x{chunk[-1]:08x}u," for chunk in chunks)
    out.extend(["};", "", "static const uint32_t nokia_frontend_resumes[]={"])
    out.extend(f"    0x{address:08x}u," for address in resume_addresses)
    out.extend(["};",
                "NOKIA_EXPORT uint32_t nokia_frontend_resume_count(void){return (uint32_t)(sizeof(nokia_frontend_resumes)/sizeof(nokia_frontend_resumes[0]));}",
                "NOKIA_EXPORT uint32_t nokia_frontend_resume_address(uint32_t index){return index<nokia_frontend_resume_count()?nokia_frontend_resumes[index]:0;}",
                "",
                "NOKIA_EXPORT int nokia_frontend_aot(uint8_t*heap,uint8_t*vtable,uint8_t*traps,",
                " uint8_t*pool,uint8_t*stack,const uint8_t*rom,uint32_t rom_base,size_t rom_size,",
                " uint32_t regs[17],uint32_t return_address,const NokiaFrontendHost*host){",
                "    NokiaFrontendState state_storage={0},*state=&state_storage;",
                "    NokiaFrontendMachine machine_storage={heap,vtable,traps,pool,stack,rom,rom_base,rom_size,0,host};",
                "    NokiaFrontendMachine*machine_ptr=&machine_storage;",
                "    nokia_frontend_dirty_mask=0;"])
    register_order = ("r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
                      "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc")
    out.extend(f"    reg_{name}=regs[{index}];"
               for index, name in enumerate(register_order))
    entry = re.search(r"if\(!reg_pc\)reg_pc=UINT64_C\((\d+)\);", prologue)
    if not entry:
        raise ValueError("frontend entry point was not found")
    out.extend(["    reg_NG=(regs[16]>>31)&1; reg_ZR=(regs[16]>>30)&1;",
                "    reg_CY=(regs[16]>>29)&1; reg_OV=(regs[16]>>28)&1;",
                f"    if(!reg_pc)reg_pc=UINT64_C({entry.group(1)});",
                "dispatch:",
                "    if(((uint32_t)reg_pc&~1u)==(return_address&~1u))goto finished;",
                "    switch((uint32_t)reg_pc&~1u){",
                "    case 0x52000000u: if(!host||!host->alloc)goto unsupported; reg_r0=host->alloc(host->context,(uint32_t)reg_r1);reg_pc=reg_lr;goto dispatch;",
                "    case 0x52000004u: if(!host||!host->free)goto unsupported; host->free(host->context,(uint32_t)reg_r1);reg_r0=0;reg_pc=reg_lr;goto dispatch;",
                "    case 0x52000008u: if(!host||!host->realloc)goto unsupported; reg_r0=host->realloc(host->context,(uint32_t)reg_r1,(uint32_t)reg_r2);reg_pc=reg_lr;goto dispatch;",
                "    case 0x5200000cu: if(!host||!host->length)goto unsupported; reg_r0=host->length(host->context,(uint32_t)reg_r1);reg_pc=reg_lr;goto dispatch;",
                "    case 0x52000180u: if(!host||!host->alloc)goto unsupported; reg_r0=host->alloc(host->context,(uint32_t)reg_r1);reg_pc=reg_lr;goto dispatch;",
                "    case 0x52000224u: { uint32_t end=(uint32_t)nokia_mem_load(&machine,reg_sp,4); reg_r0=nokia_frontend_config_blob(&machine,host,(uint32_t)reg_r1,(uint32_t)reg_r2,(uint32_t)reg_r3,end); reg_pc=reg_lr; goto dispatch; }",
                "    case 0x8019db50u: reg_r0=nokia_mem_load(&machine,0x53000010u,4);reg_pc=reg_lr;goto dispatch;",
                "    case 0x8019db88u: reg_r0=nokia_mem_load(&machine,0x53000018u,4);reg_pc=reg_lr;goto dispatch;",
                "    case 0x8019db70u: reg_r0=nokia_mem_load(&machine,0x53000014u,4);reg_pc=reg_lr;goto dispatch;",
                "    }",
                "    { uint32_t pc=(uint32_t)reg_pc&~1u; size_t lo=0,hi=sizeof(nokia_frontend_chunk_limits)/sizeof(nokia_frontend_chunk_limits[0]);",
                "      while(lo<hi){size_t mid=lo+(hi-lo)/2;if(pc<=nokia_frontend_chunk_limits[mid])hi=mid;else lo=mid+1;}",
                "      if(lo>=sizeof(nokia_frontend_chunks)/sizeof(nokia_frontend_chunks[0]))goto yielded;",
                "      int result=nokia_frontend_chunks[lo](state,machine_ptr,host);",
                "      if(result==NOKIA_FRONTEND_CONTINUE)goto dispatch;",
                "      if(result==NOKIA_FRONTEND_YIELDED)goto yielded;",
                "      goto unsupported; }"])
    tail = body[finished.start():].rstrip()
    tail = tail.rsplit("}", 1)[0].rstrip()
    out.extend([tail, "}", "#undef machine"])
    out.extend(f"#undef {name}" for name in variable_names)
    out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    args.source.write_text(split_source(source), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
