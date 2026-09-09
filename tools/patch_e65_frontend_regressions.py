#!/usr/bin/env python3
"""Add Nokia E65 frontend paths exercised by the x64 regression smoke test."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


GENERATED_PATCH_DATA = (
    Path(__file__).resolve().parent.parent
    / "native"
    / "generated"
    / "e65-frontend-regression-aot-patch.json.gz"
)

RARRAY_CLOSE_ANCHOR = (
    "    case 0x52000004u: if(!host||!host->free)goto unsupported; "
    "host->free(host->context,(uint32_t)reg_r1);reg_r0=0;"
    "reg_pc=reg_lr;goto dispatch;\n"
)
RARRAY_CLOSE_CASE = """    /* E65 ROM RArrayBase::Close (code page is not packed). */
    case 0xf814088cu: {
        uint32_t array=(uint32_t)reg_r0;
        uint32_t entries=(uint32_t)nokia_mem_load(&machine,array+4u,4);
        if(!host||!host->free)goto unsupported;
        if(!nokia_mem_store(&machine,array,0u,4))goto unsupported;
        if(entries)host->free(host->context,entries);
        if(!nokia_mem_store(&machine,array+4u,0u,4))goto unsupported;
        if(!nokia_mem_store(&machine,array+12u,0u,4))goto unsupported;
        reg_pc=reg_lr;goto dispatch;
    }
"""
OBJECT_FREE_CASE = """    /* E65 ROM operator delete (code page is not packed). */
    case 0xf812ccc0u:
        if(!host||!host->free)goto unsupported;
        if(reg_r0)host->free(host->context,(uint32_t)reg_r0);
        reg_pc=reg_lr;goto dispatch;
"""


DISPATCH_ANCHOR = "    case 0xf8400420u: goto L_f8400420;\n"
DISPATCH_LINES = """    case 0xf8400422u: goto L_f8400422;
    case 0xf8400424u: goto L_f8400424;
    case 0xf8400426u: goto L_f8400426;
    case 0xf8400428u: goto L_f8400428;
    case 0xf840042au: goto L_f840042a;
"""
BODY_ANCHOR = "L_f840042c:\n"
BODY = """L_f8400422:
    nokia_frontend_last_pc=0xf8400422u;
    reg_tmpCY = ((uint64_t)((UINT64_C(2) & UINT64_C(0xffffffff)) <= (reg_r7 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r7 & UINT64_C(0xffffffff)), (UINT64_C(2) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    u_159800 = ((uint64_t)((reg_r7 & UINT64_C(0xffffffff)) - (UINT64_C(2) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((u_159800 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((u_159800 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8400424;
L_f8400424:
    nokia_frontend_last_pc=0xf8400424u;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) { goto L_f840042c; }
    goto L_f8400426;
L_f8400426:
    nokia_frontend_last_pc=0xf8400426u;
    u_151300 = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)) + (UINT64_C(8) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r0 = ((uint64_t)(nokia_mem_load(&machine, (u_151300 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_f8400428;
L_f8400428:
    nokia_frontend_last_pc=0xf8400428u;
    reg_tmpCY = ((uint64_t)((UINT64_C(0) & UINT64_C(0xffffffff)) <= (reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    u_159800 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) - (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((u_159800 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((u_159800 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f840042a;
L_f840042a:
    nokia_frontend_last_pc=0xf840042au;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) { goto L_f840043e; }
    goto L_f840042c;
"""
RETURN_DISPATCH_ANCHOR = "    case 0xf840e34au: goto L_f840e34a;\n"
RETURN_DISPATCH_LINES = """    case 0xf840e34cu: goto L_f840e34c;
    case 0xf840e34eu: goto L_f840e34e;
"""
RETURN_BODY_ANCHOR = "L_f840e350:\n"
RETURN_BODY = """L_f840e34c:
    nokia_frontend_last_pc=0xf840e34cu;
    reg_r0 = ((uint64_t)((UINT64_C(252) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f840e34e;
L_f840e34e:
    nokia_frontend_last_pc=0xf840e34eu;
    reg_mult_addr = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r4 = ((uint64_t)(nokia_mem_load(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r5 = ((uint64_t)(nokia_mem_load(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r6 = ((uint64_t)(nokia_mem_load(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_pc = ((uint64_t)(nokia_mem_load(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_sp = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_0 = ((uint64_t)((reg_pc & UINT64_C(0xffffffff)) & (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_TB = ((uint64_t)((u_0 & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_pc = ((uint64_t)((reg_pc & UINT64_C(0xffffffff)) & (UINT64_C(4294967294) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_pc=(reg_pc & UINT64_C(0xffffffff));
    return NOKIA_FRONTEND_CONTINUE;
"""
CLASS_DISPATCH_ANCHOR = "    case 0xf84094fcu: goto L_f84094fc;\n"
CLASS_DISPATCH_LINES = """    case 0xf84094feu: goto L_f84094fe;
    case 0xf8409500u: goto L_f8409500;
"""
CLASS_BODY_ANCHOR = "L_f8409502:\n"
CLASS_BODY = """L_f84094fe:
    nokia_frontend_last_pc=0xf84094feu;
    reg_r6 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r6 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r6 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8409500;
L_f8409500:
    nokia_frontend_last_pc=0xf8409500u;
    goto L_f8409560;
"""
LOOKUP_DISPATCH_ANCHOR = "    case 0xf8408f5cu: goto L_f8408f5c;\n"
LOOKUP_DISPATCH_LINES = """    case 0xf8408f5eu: goto L_f8408f5e;
    case 0xf8408f64u: goto L_f8408f64;
    case 0xf8408f66u: goto L_f8408f66;
    case 0xf8408f6au: goto L_f8408f6a;
"""
LOOKUP_BODY_ANCHOR = "L_f8408f60:\n"
LOOKUP_BODY = """L_f8408f5e:
    nokia_frontend_last_pc=0xf8408f5eu;
    goto L_f8408f64;
L_f8408f64:
    nokia_frontend_last_pc=0xf8408f64u;
    reg_r0 = ((uint64_t)((reg_r7 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8408f66;
L_f8408f66:
    nokia_frontend_last_pc=0xf8408f66u;
    reg_lr = ((uint64_t)((UINT64_C(4164980586) & UINT64_C(0xffffffff)) | (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_TB = ((uint64_t)((UINT64_C(1) & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_lr=UINT64_C(4164980587);
    reg_pc=UINT64_C(4164981078); return NOKIA_FRONTEND_CONTINUE;
L_f8408f6a:
    nokia_frontend_last_pc=0xf8408f6au;
    goto L_f8408f74;
"""
HELPER_DISPATCH_ANCHOR = "    case 0xf8409154u: goto L_f8409154;\n"
HELPER_DISPATCH_LINES = """    case 0xf8409156u: goto L_f8409156;
    case 0xf8409158u: goto L_f8409158;
    case 0xf840915au: goto L_f840915a;
    case 0xf840915cu: goto L_f840915c;
    case 0xf840915eu: goto L_f840915e;
    case 0xf8409160u: goto L_f8409160;
    case 0xf8409162u: goto L_f8409162;
    case 0xf8409164u: goto L_f8409164;
    case 0xf8409166u: goto L_f8409166;
    case 0xf8409168u: goto L_f8409168;
    case 0xf840916au: goto L_f840916a;
    case 0xf840916cu: goto L_f840916c;
    case 0xf840916eu: goto L_f840916e;
    case 0xf8409170u: goto L_f8409170;
    case 0xf8409172u: goto L_f8409172;
    case 0xf8409174u: goto L_f8409174;
    case 0xf8409176u: goto L_f8409176;
    case 0xf8409178u: goto L_f8409178;
    case 0xf840917au: goto L_f840917a;
    case 0xf840917cu: goto L_f840917c;
    case 0xf840917eu: goto L_f840917e;
"""
HELPER_BODY_ANCHOR = "L_f8409180:\n"
HELPER_BODY = """L_f8409156:
    nokia_frontend_last_pc=0xf8409156u;
    reg_mult_addr = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) - (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), (reg_lr & UINT64_C(0xffffffff)), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) - (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), (reg_r4 & UINT64_C(0xffffffff)), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    reg_sp = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    goto L_f8409158;
L_f8409158:
    nokia_frontend_last_pc=0xf8409158u;
    reg_r2 = ((uint64_t)((UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r2 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r2 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f840915a;
L_f840915a:
    nokia_frontend_last_pc=0xf840915au;
    reg_r3 = ((uint64_t)((UINT64_C(2) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r3 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r3 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f840915c;
L_f840915c:
    nokia_frontend_last_pc=0xf840915cu;
    u_150a00 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(12) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r0 = ((uint64_t)(nokia_mem_load(&machine, (u_150a00 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_f840915e;
L_f840915e:
    nokia_frontend_last_pc=0xf840915eu;
    reg_r4 = ((uint64_t)((UINT64_C(3) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r4 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8409160;
L_f8409160:
    nokia_frontend_last_pc=0xf8409160u;
    goto L_f840917a;
L_f8409162:
    nokia_frontend_last_pc=0xf8409162u;
    u_150a00 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(12) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r1 = ((uint64_t)(nokia_mem_load(&machine, (u_150a00 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_f8409164;
L_f8409164:
    nokia_frontend_last_pc=0xf8409164u;
    u_150e00 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) + (UINT64_C(28) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_15b100 = ((uint64_t)(nokia_mem_load(&machine, (u_150e00 & UINT64_C(0xffffffff)), 1))) & UINT64_C(0xff);
    reg_r1 = ((uint64_t)((u_15b100 & UINT64_C(0xff)))) & UINT64_C(0xffffffff);
    goto L_f8409166;
L_f8409166:
    nokia_frontend_last_pc=0xf8409166u;
    reg_tmpCY = ((uint64_t)((UINT64_C(252) & UINT64_C(0xffffffff)) <= (reg_r1 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(252) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    u_159800 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) - (UINT64_C(252) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((u_159800 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((u_159800 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8409168;
L_f8409168:
    nokia_frontend_last_pc=0xf8409168u;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) { goto L_f840916e; }
    goto L_f840916a;
L_f840916a:
    nokia_frontend_last_pc=0xf840916au;
    u_150e00 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(26) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_1af700 = ((uint64_t)((reg_r2 & UINT64_C(0xffffffff)) >> (8 * (UINT64_C(0) & UINT64_C(0xffffffff))))) & UINT64_C(0xff);
    if (!nokia_mem_store(&machine, (u_150e00 & UINT64_C(0xffffffff)), (u_1af700 & UINT64_C(0xff)), 1)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f840916c;
L_f840916c:
    nokia_frontend_last_pc=0xf840916cu;
    goto L_f8409178;
L_f840916e:
    nokia_frontend_last_pc=0xf840916eu;
    reg_tmpCY = ((uint64_t)((UINT64_C(253) & UINT64_C(0xffffffff)) <= (reg_r1 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(253) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    u_159800 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) - (UINT64_C(253) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((u_159800 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((u_159800 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8409170;
L_f8409170:
    nokia_frontend_last_pc=0xf8409170u;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) { goto L_f8409176; }
    goto L_f8409172;
L_f8409172:
    nokia_frontend_last_pc=0xf8409172u;
    u_150e00 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(26) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_1af700 = ((uint64_t)((reg_r3 & UINT64_C(0xffffffff)) >> (8 * (UINT64_C(0) & UINT64_C(0xffffffff))))) & UINT64_C(0xff);
    if (!nokia_mem_store(&machine, (u_150e00 & UINT64_C(0xffffffff)), (u_1af700 & UINT64_C(0xff)), 1)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8409174;
L_f8409174:
    nokia_frontend_last_pc=0xf8409174u;
    goto L_f8409178;
L_f8409176:
    nokia_frontend_last_pc=0xf8409176u;
    u_150e00 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(26) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_1af700 = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)) >> (8 * (UINT64_C(0) & UINT64_C(0xffffffff))))) & UINT64_C(0xff);
    if (!nokia_mem_store(&machine, (u_150e00 & UINT64_C(0xffffffff)), (u_1af700 & UINT64_C(0xff)), 1)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8409178;
L_f8409178:
    nokia_frontend_last_pc=0xf8409178u;
    u_150a00 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r0 = ((uint64_t)(nokia_mem_load(&machine, (u_150a00 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_f840917a;
L_f840917a:
    nokia_frontend_last_pc=0xf840917au;
    reg_tmpCY = ((uint64_t)((UINT64_C(0) & UINT64_C(0xffffffff)) <= (reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    u_159800 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) - (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((u_159800 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((u_159800 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f840917c;
L_f840917c:
    nokia_frontend_last_pc=0xf840917cu;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) { goto L_f8409162; }
    goto L_f840917e;
L_f840917e:
    nokia_frontend_last_pc=0xf840917eu;
    reg_mult_addr = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r4 = ((uint64_t)(nokia_mem_load(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_pc = ((uint64_t)(nokia_mem_load(&machine, (reg_mult_addr & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_mult_addr = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)) + (UINT64_C(4) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_sp = ((uint64_t)((reg_mult_addr & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_0 = ((uint64_t)((reg_pc & UINT64_C(0xffffffff)) & (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_TB = ((uint64_t)((u_0 & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_pc = ((uint64_t)((reg_pc & UINT64_C(0xffffffff)) & (UINT64_C(4294967294) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_pc=(reg_pc & UINT64_C(0xffffffff));
    return NOKIA_FRONTEND_CONTINUE;
"""
RANGE_DISPATCH_ANCHOR = "    case 0xf8400f2au: goto L_f8400f2a;\n"
RANGE_DISPATCH_LINES = """    case 0xf8400f2cu: goto L_f8400f2c;
    case 0xf8400f2eu: goto L_f8400f2e;
"""
RANGE_BODY_ANCHOR = "L_f8400f30:\n"
RANGE_BODY = """L_f8400f2c:
    nokia_frontend_last_pc=0xf8400f2cu;
    reg_r0 = ((uint64_t)((UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8400f2e;
L_f8400f2e:
    nokia_frontend_last_pc=0xf8400f2eu;
    u_0 = ((uint64_t)((reg_lr & UINT64_C(0xffffffff)) & (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_TB = ((uint64_t)((u_0 & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_pc = ((uint64_t)((reg_lr & UINT64_C(0xffffffff)) & (UINT64_C(4294967294) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_pc=(reg_pc & UINT64_C(0xffffffff));
    return NOKIA_FRONTEND_CONTINUE;
"""

COUNT_NORMALIZE_DISPATCH_ANCHOR = "    case 0xf840064au: goto L_f840064a;\n"
COUNT_NORMALIZE_DISPATCH_LINES = """    case 0xf840064cu: goto L_f840064c;
    case 0xf840064eu: goto L_f840064e;
    case 0xf8400650u: goto L_f8400650;
"""
COUNT_NORMALIZE_BODY_ANCHOR = "L_f8400652:\n"
COUNT_NORMALIZE_BODY = """L_f840064c:
    nokia_frontend_last_pc=0xf840064cu;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) + UINT64_C(1)) & UINT64_C(0xffffffff);
    goto L_f840064e;
L_f840064e:
    nokia_frontend_last_pc=0xf840064eu;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) << 16) & UINT64_C(0xffffffff);
    goto L_f8400650;
L_f8400650:
    nokia_frontend_last_pc=0xf8400650u;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) >> 16) & UINT64_C(0xffffffff);
    goto L_f8400652;
"""

LONG_TEXT_INCREMENT_DISPATCH_ANCHOR = (
    "    case 0xf83fcaa4u: goto L_f83fcaa4;\n"
)
LONG_TEXT_INCREMENT_DISPATCH_LINES = (
    "    case 0xf83fcaa6u: goto L_f83fcaa6;\n"
)
LONG_TEXT_INCREMENT_BODY_ANCHOR = "L_f83fcaa8:\n"
LONG_TEXT_INCREMENT_BODY = """L_f83fcaa6:
    nokia_frontend_last_pc=0xf83fcaa6u;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r5 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r5 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r5 = ((uint64_t)((reg_r5 & UINT64_C(0xffffffff)) + (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r5 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r5 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f83fcaa8;
"""

LONG_TEXT_FLAG_DISPATCH_ANCHOR = "    case 0xf8400d78u: goto L_f8400d78;\n"
LONG_TEXT_FLAG_DISPATCH_LINES = """    case 0xf8400d7au: goto L_f8400d7a;
    case 0xf8400d7cu: goto L_f8400d7c;
    case 0xf8400d7eu: goto L_f8400d7e;
"""
LONG_TEXT_FLAG_BODY_ANCHOR = "L_f8400d82:\n"
LONG_TEXT_FLAG_BODY = """L_f8400d7a:
    nokia_frontend_last_pc=0xf8400d7au;
    reg_r1 = ((uint64_t)((UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r1 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8400d7c;
L_f8400d7c:
    nokia_frontend_last_pc=0xf8400d7cu;
    reg_r0 = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8400d7e;
L_f8400d7e:
    nokia_frontend_last_pc=0xf8400d7eu;
    reg_lr = ((uint64_t)((UINT64_C(4164947330) & UINT64_C(0xffffffff)) | (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_TB = ((uint64_t)((UINT64_C(1) & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_lr=UINT64_C(4164947331);
    reg_pc=UINT64_C(4164946334); return NOKIA_FRONTEND_CONTINUE;
"""

LONG_TEXT_TABLE_DISPATCH_ANCHOR = "    case 0xf840067cu: goto L_f840067c;\n"
LONG_TEXT_TABLE_DISPATCH_LINES = """    case 0xf840067eu: goto L_f840067e;
    case 0xf8400680u: goto L_f8400680;
    case 0xf8400682u: goto L_f8400682;
    case 0xf8400684u: goto L_f8400684;
    case 0xf8400686u: goto L_f8400686;
"""
LONG_TEXT_TABLE_BODY_ANCHOR = "L_f8400688:\n"
LONG_TEXT_TABLE_BODY = """L_f840067e:
    nokia_frontend_last_pc=0xf840067eu;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    reg_r2 = nokia_mem_load(&machine, u_150a00, 4) & UINT64_C(0xffffffff);
    goto L_f8400680;
L_f8400680:
    nokia_frontend_last_pc=0xf8400680u;
    reg_r3 = ((reg_r1 & UINT64_C(0xffffffff)) << 1) & UINT64_C(0xffffffff);
    goto L_f8400682;
L_f8400682:
    nokia_frontend_last_pc=0xf8400682u;
    u_151000 = ((reg_r2 & UINT64_C(0xffffffff)) + (reg_r3 & UINT64_C(0xffffffff))) & UINT64_C(0xffffffff);
    u_15b700 = nokia_mem_load(&machine, u_151000, 2) & UINT64_C(0xffff);
    reg_r6 = u_15b700;
    goto L_f8400684;
L_f8400684:
    nokia_frontend_last_pc=0xf8400684u;
    reg_r6 = ((reg_r6 & UINT64_C(0xffffffff)) + (reg_r0 & UINT64_C(0xffffffff))) & UINT64_C(0xffffffff);
    goto L_f8400686;
L_f8400686:
    nokia_frontend_last_pc=0xf8400686u;
    u_151000 = ((reg_r2 & UINT64_C(0xffffffff)) + (reg_r3 & UINT64_C(0xffffffff))) & UINT64_C(0xffffffff);
    u_1afd00 = reg_r6 & UINT64_C(0xffff);
    if (!nokia_mem_store(&machine, u_151000, u_1afd00, 2)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8400688;
"""

LONG_TEXT_LOOKUP_DISPATCH_ANCHOR = "    case 0xf840065eu: goto L_f840065e;\n"
LONG_TEXT_LOOKUP_DISPATCH_LINES = """    case 0xf8400660u: goto L_f8400660;
    case 0xf8400662u: goto L_f8400662;
    case 0xf8400664u: goto L_f8400664;
    case 0xf8400666u: goto L_f8400666;
    case 0xf8400668u: goto L_f8400668;
    case 0xf840066au: goto L_f840066a;
    case 0xf840066cu: goto L_f840066c;
    case 0xf840066eu: goto L_f840066e;
    case 0xf8400670u: goto L_f8400670;
    case 0xf8400672u: goto L_f8400672;
    case 0xf8400674u: goto L_f8400674;
    case 0xf8400676u: goto L_f8400676;
    case 0xf8400678u: goto L_f8400678;
"""
LONG_TEXT_LOOKUP_BODY_ANCHOR = "L_f840067a:\n"
LONG_TEXT_LOOKUP_BODY = """L_f8400660:
    nokia_frontend_last_pc=0xf8400660u;
    u_151000 = ((reg_r3 & UINT64_C(0xffffffff)) + (reg_r2 & UINT64_C(0xffffffff))) & UINT64_C(0xffffffff);
    reg_r1 = nokia_mem_load(&machine, u_151000, 4) & UINT64_C(0xffffffff);
    goto L_f8400662;
L_f8400662:
    nokia_frontend_last_pc=0xf8400662u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(48)) & UINT64_C(0xffffffff);
    reg_r3 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f8400664;
L_f8400664:
    nokia_frontend_last_pc=0xf8400664u;
    reg_r2 = nokia_mem_load(&machine, reg_r1 & UINT64_C(0xffffffff), 2) & UINT64_C(0xffff);
    goto L_f8400666;
L_f8400666:
    nokia_frontend_last_pc=0xf8400666u;
    reg_ZR = ((reg_r2 & UINT64_C(0xffffffff)) == (reg_r3 & UINT64_C(0xffffffff)));
    goto L_f8400668;
L_f8400668:
    nokia_frontend_last_pc=0xf8400668u;
    if (!(reg_ZR & UINT64_C(0xff))) goto L_f840067a;
    goto L_f840066a;
L_f840066a:
    nokia_frontend_last_pc=0xf840066au;
    reg_r6 = reg_r12 & UINT64_C(0xffffffff);
    goto L_f840066c;
L_f840066c:
    nokia_frontend_last_pc=0xf840066cu;
    reg_r2 = ((reg_r6 & UINT64_C(0xffffffff)) << 1) & UINT64_C(0xffffffff);
    goto L_f840066e;
L_f840066e:
    nokia_frontend_last_pc=0xf840066eu;
    reg_r2 = ((reg_r2 & UINT64_C(0xffffffff)) - UINT64_C(2)) & UINT64_C(0xffffffff);
    goto L_f8400670;
L_f8400670:
    nokia_frontend_last_pc=0xf8400670u;
    u_151000 = ((reg_r1 & UINT64_C(0xffffffff)) + (reg_r2 & UINT64_C(0xffffffff))) & UINT64_C(0xffffffff);
    reg_r1 = nokia_mem_load(&machine, u_151000, 2) & UINT64_C(0xffff);
    goto L_f8400672;
L_f8400672:
    nokia_frontend_last_pc=0xf8400672u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(50)) & UINT64_C(0xffffffff);
    reg_r2 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f8400674;
L_f8400674:
    nokia_frontend_last_pc=0xf8400674u;
    reg_ZR = ((reg_r1 & UINT64_C(0xffffffff)) == (reg_r2 & UINT64_C(0xffffffff)));
    goto L_f8400676;
L_f8400676:
    nokia_frontend_last_pc=0xf8400676u;
    if (!(reg_ZR & UINT64_C(0xff))) goto L_f840067a;
    goto L_f8400678;
L_f8400678:
    nokia_frontend_last_pc=0xf8400678u;
    reg_r0 = 0;
    goto L_f840067a;
"""

LONG_SETTINGS_LOOKUP_DISPATCH_ANCHOR = "    case 0xf8400c42u: goto L_f8400c42;\n"
LONG_SETTINGS_LOOKUP_DISPATCH_LINES = """    case 0xf8400c44u: goto L_f8400c44;
    case 0xf8400c46u: goto L_f8400c46;
    case 0xf8400c48u: goto L_f8400c48;
"""
LONG_SETTINGS_LOOKUP_BODY_ANCHOR = "L_f8400c4a:\n"
LONG_SETTINGS_LOOKUP_BODY = """L_f8400c44:
    nokia_frontend_last_pc=0xf8400c44u;
    reg_r1 = ((reg_r1 & UINT64_C(0xffffffff)) + UINT64_C(2)) & UINT64_C(0xffffffff);
    goto L_f8400c46;
L_f8400c46:
    nokia_frontend_last_pc=0xf8400c46u;
    u_151000 = ((reg_r0 & UINT64_C(0xffffffff)) + (reg_r1 & UINT64_C(0xffffffff))) & UINT64_C(0xffffffff);
    reg_r1 = nokia_mem_load(&machine, u_151000, 2) & UINT64_C(0xffff);
    goto L_f8400c48;
L_f8400c48:
    nokia_frontend_last_pc=0xf8400c48u;
    goto L_f8400c4c;
"""

LONG_SETTINGS_FLAG_DISPATCH_ANCHOR = "    case 0xf83fc11eu: goto L_f83fc11e;\n"
LONG_SETTINGS_FLAG_DISPATCH_LINES = "    case 0xf83fc120u: goto L_f83fc120;\n"
LONG_SETTINGS_FLAG_BODY_ANCHOR = "L_f83fc122:\n"
LONG_SETTINGS_FLAG_BODY = """L_f83fc120:
    nokia_frontend_last_pc=0xf83fc120u;
    reg_r4 = 1;
    goto L_f83fc122;
"""

LONG_ERROR_TABLE_DISPATCH_ANCHOR = "    case 0xf8400d00u: goto L_f8400d00;\n"
LONG_ERROR_TABLE_DISPATCH_LINES = """    case 0xf8400d02u: goto L_f8400d02;
    case 0xf8400d04u: goto L_f8400d04;
"""
LONG_ERROR_TABLE_BODY_ANCHOR = "L_f8400d06:\n"
LONG_ERROR_TABLE_BODY = """L_f8400d02:
    nokia_frontend_last_pc=0xf8400d02u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(54)) & UINT64_C(0xffffffff);
    reg_r1 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f8400d04;
L_f8400d04:
    nokia_frontend_last_pc=0xf8400d04u;
    goto L_f8400d08;
"""

LONG_TEXT_COPY_DISPATCH_ANCHOR = "    case 0xf83fcc10u: goto L_f83fcc10;\n"
LONG_TEXT_COPY_DISPATCH_LINES = """    case 0xf83fcc12u: goto L_f83fcc12;
    case 0xf83fcc14u: goto L_f83fcc14;
    case 0xf83fcc16u: goto L_f83fcc16;
    case 0xf83fcc1au: goto L_f83fcc1a;
"""
LONG_TEXT_COPY_BODY_ANCHOR = "L_f83fcc1c:\n"
LONG_TEXT_COPY_BODY = """L_f83fcc12:
    nokia_frontend_last_pc=0xf83fcc12u;
    u_151300 = ((reg_sp & UINT64_C(0xffffffff)) + UINT64_C(76)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_151300, 4) & UINT64_C(0xffffffff);
    goto L_f83fcc14;
L_f83fcc14:
    nokia_frontend_last_pc=0xf83fcc14u;
    u_151300 = ((reg_sp & UINT64_C(0xffffffff)) + UINT64_C(32)) & UINT64_C(0xffffffff);
    reg_r1 = nokia_mem_load(&machine, u_151300, 4) & UINT64_C(0xffffffff);
    goto L_f83fcc16;
L_f83fcc16:
    nokia_frontend_last_pc=0xf83fcc16u;
    reg_TB = 1;
    reg_lr = UINT64_C(4164930587);
    reg_pc = UINT64_C(4164931292);
    return NOKIA_FRONTEND_CONTINUE;
L_f83fcc1a:
    nokia_frontend_last_pc=0xf83fcc1au;
    reg_r4 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(1)) & UINT64_C(0xffffffff);
    goto L_f83fcc1c;
"""

LONG_ERROR_ASSERT_DISPATCH_ANCHOR = "    case 0xf84071aau: goto L_f84071aa;\n"
LONG_ERROR_ASSERT_DISPATCH_LINES = """    case 0xf84071e2u: goto L_f84071e2;
    case 0xf84071e4u: goto L_f84071e4;
    case 0xf84071e6u: goto L_f84071e6;
    case 0xf84071e8u: goto L_f84071e8;
    case 0xf84071eau: goto L_f84071ea;
    case 0xf84071ecu: goto L_f84071ec;
    case 0xf84071f0u: goto L_f84071f0;
"""
LONG_ERROR_ASSERT_BODY_ANCHOR = "L_f84071f2:\n"
LONG_ERROR_ASSERT_BODY = """L_f84071e2:
    nokia_frontend_last_pc=0xf84071e2u;
    reg_ZR = ((reg_r0 & UINT64_C(0xffffffff)) == 0);
    goto L_f84071e4;
L_f84071e4:
    nokia_frontend_last_pc=0xf84071e4u;
    reg_mult_addr = reg_sp & UINT64_C(0xffffffff);
    reg_mult_addr = (reg_mult_addr - UINT64_C(4)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, reg_mult_addr, reg_lr, 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    reg_mult_addr = (reg_mult_addr - UINT64_C(4)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, reg_mult_addr, reg_r4, 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    reg_sp = reg_mult_addr;
    goto L_f84071e6;
L_f84071e6:
    nokia_frontend_last_pc=0xf84071e6u;
    if (reg_ZR & UINT64_C(0xff)) goto L_f84071f0;
    goto L_f84071e8;
L_f84071e8:
    nokia_frontend_last_pc=0xf84071e8u;
    reg_r0 = UINT64_C(18);
    goto L_f84071ea;
L_f84071ea:
    nokia_frontend_last_pc=0xf84071eau;
    reg_r0 = (~reg_r0) & UINT64_C(0xffffffff);
    goto L_f84071ec;
L_f84071ec:
    nokia_frontend_last_pc=0xf84071ecu;
    reg_lr = UINT64_C(4164973041);
    u_a7f00 = nokia_mem_load(&machine, UINT64_C(4165005524), 4) & UINT64_C(0xffffffff);
    reg_TB = ((u_a7f00 & UINT64_C(1)) != 0);
    reg_pc = u_a7f00 & UINT64_C(0xfffffffe);
    return NOKIA_FRONTEND_CONTINUE;
L_f84071f0:
    nokia_frontend_last_pc=0xf84071f0u;
    reg_mult_addr = reg_sp & UINT64_C(0xffffffff);
    reg_r4 = nokia_mem_load(&machine, reg_mult_addr, 4) & UINT64_C(0xffffffff);
    reg_mult_addr = (reg_mult_addr + UINT64_C(4)) & UINT64_C(0xffffffff);
    reg_pc = nokia_mem_load(&machine, reg_mult_addr, 4) & UINT64_C(0xffffffff);
    reg_mult_addr = (reg_mult_addr + UINT64_C(4)) & UINT64_C(0xffffffff);
    reg_sp = reg_mult_addr;
    reg_TB = ((reg_pc & UINT64_C(1)) != 0);
    reg_pc &= UINT64_C(0xfffffffe);
    return NOKIA_FRONTEND_CONTINUE;
"""

LONG_ERROR_OBJECT_DISPATCH_ANCHOR = "    case 0xf8408cd0u: goto L_f8408cd0;\n"
LONG_ERROR_OBJECT_DISPATCH_LINES = """    case 0xf8408cd2u: goto L_f8408cd2;
    case 0xf8408cd4u: goto L_f8408cd4;
    case 0xf8408cd6u: goto L_f8408cd6;
    case 0xf8408cdau: goto L_f8408cda;
    case 0xf8408cdcu: goto L_f8408cdc;
    case 0xf8408cdeu: goto L_f8408cde;
    case 0xf8408ce0u: goto L_f8408ce0;
    case 0xf8408ce2u: goto L_f8408ce2;
    case 0xf8408ce6u: goto L_f8408ce6;
    case 0xf8408ce8u: goto L_f8408ce8;
    case 0xf8408ceau: goto L_f8408cea;
    case 0xf8408cecu: goto L_f8408cec;
"""
LONG_ERROR_OBJECT_BODY_ANCHOR = "L_f8408cee:\n"
LONG_ERROR_OBJECT_BODY = """L_f8408cd2:
    nokia_frontend_last_pc=0xf8408cd2u;
    reg_r1 = ((reg_r0 & UINT64_C(0xffffffff)) << 4) & UINT64_C(0xffffffff);
    goto L_f8408cd4;
L_f8408cd4:
    nokia_frontend_last_pc=0xf8408cd4u;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150a00, 4) & UINT64_C(0xffffffff);
    goto L_f8408cd6;
L_f8408cd6:
    nokia_frontend_last_pc=0xf8408cd6u;
    reg_TB = 1;
    reg_lr = UINT64_C(4164979931);
    reg_pc = UINT64_C(4164973080);
    return NOKIA_FRONTEND_CONTINUE;
L_f8408cda:
    nokia_frontend_last_pc=0xf8408cdau;
    reg_r5 = reg_r0 & UINT64_C(0xffffffff);
    reg_ZR = (reg_r5 == 0);
    reg_NG = ((reg_r5 & UINT64_C(0x80000000)) != 0);
    goto L_f8408cdc;
L_f8408cdc:
    nokia_frontend_last_pc=0xf8408cdcu;
    if (!(reg_ZR & UINT64_C(0xff))) goto L_f8408ce6;
    goto L_f8408cde;
L_f8408cde:
    nokia_frontend_last_pc=0xf8408cdeu;
    reg_r0 = 1;
    goto L_f8408ce0;
L_f8408ce0:
    nokia_frontend_last_pc=0xf8408ce0u;
    reg_r1 = UINT64_C(4164980508);
    goto L_f8408ce2;
L_f8408ce2:
    nokia_frontend_last_pc=0xf8408ce2u;
    reg_TB = 1;
    reg_lr = UINT64_C(4164979943);
    reg_pc = UINT64_C(4164973026);
    return NOKIA_FRONTEND_CONTINUE;
L_f8408ce6:
    nokia_frontend_last_pc=0xf8408ce6u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f8408ce8;
L_f8408ce8:
    nokia_frontend_last_pc=0xf8408ce8u;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) << 1) & UINT64_C(0xffffffff);
    goto L_f8408cea;
L_f8408cea:
    nokia_frontend_last_pc=0xf8408ceau;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150c00, reg_r0 & UINT64_C(0xffff), 2)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8408cec;
L_f8408cec:
    nokia_frontend_last_pc=0xf8408cecu;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150a00, reg_r5 & UINT64_C(0xffffffff), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8408cee;
"""

LONG_ERROR_SECOND_DISPATCH_ANCHOR = "    case 0xf8408638u: goto L_f8408638;\n"
LONG_ERROR_SECOND_DISPATCH_LINES = """    case 0xf840863au: goto L_f840863a;
    case 0xf840863cu: goto L_f840863c;
    case 0xf840863eu: goto L_f840863e;
    case 0xf8408642u: goto L_f8408642;
    case 0xf8408644u: goto L_f8408644;
    case 0xf8408646u: goto L_f8408646;
    case 0xf8408648u: goto L_f8408648;
    case 0xf840864au: goto L_f840864a;
    case 0xf840864eu: goto L_f840864e;
    case 0xf8408650u: goto L_f8408650;
    case 0xf8408652u: goto L_f8408652;
    case 0xf8408654u: goto L_f8408654;
"""
LONG_ERROR_SECOND_BODY_ANCHOR = "L_f8408656:\n"
LONG_ERROR_SECOND_BODY = """L_f840863a:
    nokia_frontend_last_pc=0xf840863au;
    reg_r1 = ((reg_r0 & UINT64_C(0xffffffff)) << 4) & UINT64_C(0xffffffff);
    goto L_f840863c;
L_f840863c:
    nokia_frontend_last_pc=0xf840863cu;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150a00, 4) & UINT64_C(0xffffffff);
    goto L_f840863e;
L_f840863e:
    nokia_frontend_last_pc=0xf840863eu;
    reg_TB = 1;
    reg_lr = UINT64_C(4164978243);
    reg_pc = UINT64_C(4164973080);
    return NOKIA_FRONTEND_CONTINUE;
L_f8408642:
    nokia_frontend_last_pc=0xf8408642u;
    reg_r5 = reg_r0 & UINT64_C(0xffffffff);
    reg_ZR = (reg_r5 == 0);
    reg_NG = ((reg_r5 & UINT64_C(0x80000000)) != 0);
    goto L_f8408644;
L_f8408644:
    nokia_frontend_last_pc=0xf8408644u;
    if (!(reg_ZR & UINT64_C(0xff))) goto L_f840864e;
    goto L_f8408646;
L_f8408646:
    nokia_frontend_last_pc=0xf8408646u;
    reg_r0 = 1;
    goto L_f8408648;
L_f8408648:
    nokia_frontend_last_pc=0xf8408648u;
    reg_r1 = UINT64_C(4164978468);
    goto L_f840864a;
L_f840864a:
    nokia_frontend_last_pc=0xf840864au;
    reg_TB = 1;
    reg_lr = UINT64_C(4164978255);
    reg_pc = UINT64_C(4164973026);
    return NOKIA_FRONTEND_CONTINUE;
L_f840864e:
    nokia_frontend_last_pc=0xf840864eu;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f8408650;
L_f8408650:
    nokia_frontend_last_pc=0xf8408650u;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) << 1) & UINT64_C(0xffffffff);
    goto L_f8408652;
L_f8408652:
    nokia_frontend_last_pc=0xf8408652u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150c00, reg_r0 & UINT64_C(0xffff), 2)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8408654;
L_f8408654:
    nokia_frontend_last_pc=0xf8408654u;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150a00, reg_r5 & UINT64_C(0xffffffff), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f8408656;
"""

ARABIC_LATIN_DISPATCH_ANCHOR = (
    "    case 0xf83fe4d6u: goto L_f83fe4d6;\n"
)
ARABIC_LATIN_DISPATCH_LINE = (
    "    case 0xf83fe4d8u: goto L_f83fe4d8;\n"
)
ARABIC_LATIN_BODY_ANCHOR = "L_f83fe4e2:\n"
ARABIC_LATIN_BODY = """L_f83fe4d8:
    nokia_frontend_last_pc=0xf83fe4d8u;
    goto L_f83fe4e2;
"""

ARABIC_LATIN_ARM_DISPATCH_ANCHOR = (
    "    case 0xf83fec30u: goto L_f83fec30;\n"
)
ARABIC_LATIN_ARM_DISPATCH_LINE = (
    "    case 0xf83fec32u: goto L_f83fec32;\n"
)
ARABIC_LATIN_ARM_BODY_ANCHOR = "L_f83fec34:\n"
ARABIC_LATIN_ARM_BODY = """L_f83fec32:
    nokia_frontend_last_pc=0xf83fec32u;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r1 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) + (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r1 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f83fec34;
"""


def add_patch(
    text: str,
    *,
    name: str,
    sentinel: str,
    dispatch_anchor: str,
    dispatch_lines: str,
    body_anchor: str,
    body: str,
) -> tuple[str, bool]:
    """Insert one self-contained patch while preserving idempotence."""
    if sentinel in text:
        return text, False
    if text.count(dispatch_anchor) != 1:
        raise SystemExit(f"{name} dispatch anchor is missing or ambiguous")
    if text.count(body_anchor) != 1:
        raise SystemExit(f"{name} body anchor is missing or ambiguous")
    text = text.replace(dispatch_anchor, dispatch_anchor + dispatch_lines, 1)
    text = text.replace(body_anchor, body + body_anchor, 1)
    return text, True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")
    patches = (
        (
            "E65 Einstellungen fallthrough",
            "L_f8400422:",
            DISPATCH_ANCHOR,
            DISPATCH_LINES,
            BODY_ANCHOR,
            BODY,
        ),
        (
            "E65 Einstellungen return",
            "L_f840e34c:",
            RETURN_DISPATCH_ANCHOR,
            RETURN_DISPATCH_LINES,
            RETURN_BODY_ANCHOR,
            RETURN_BODY,
        ),
        (
            "E65 character class",
            "L_f84094fe:",
            CLASS_DISPATCH_ANCHOR,
            CLASS_DISPATCH_LINES,
            CLASS_BODY_ANCHOR,
            CLASS_BODY,
        ),
        (
            "E65 lookup",
            "L_f8408f5e:",
            LOOKUP_DISPATCH_ANCHOR,
            LOOKUP_DISPATCH_LINES,
            LOOKUP_BODY_ANCHOR,
            LOOKUP_BODY,
        ),
        (
            "E65 lookup helper",
            "L_f8409156:",
            HELPER_DISPATCH_ANCHOR,
            HELPER_DISPATCH_LINES,
            HELPER_BODY_ANCHOR,
            HELPER_BODY,
        ),
        (
            "E65 range helper",
            "L_f8400f2c:",
            RANGE_DISPATCH_ANCHOR,
            RANGE_DISPATCH_LINES,
            RANGE_BODY_ANCHOR,
            RANGE_BODY,
        ),
        (
            "E65 count normalization",
            "L_f840064c:",
            COUNT_NORMALIZE_DISPATCH_ANCHOR,
            COUNT_NORMALIZE_DISPATCH_LINES,
            COUNT_NORMALIZE_BODY_ANCHOR,
            COUNT_NORMALIZE_BODY,
        ),
        (
            "E65 long-text increment",
            "L_f83fcaa6:",
            LONG_TEXT_INCREMENT_DISPATCH_ANCHOR,
            LONG_TEXT_INCREMENT_DISPATCH_LINES,
            LONG_TEXT_INCREMENT_BODY_ANCHOR,
            LONG_TEXT_INCREMENT_BODY,
        ),
        (
            "E65 long-text flag path",
            "L_f8400d7a:",
            LONG_TEXT_FLAG_DISPATCH_ANCHOR,
            LONG_TEXT_FLAG_DISPATCH_LINES,
            LONG_TEXT_FLAG_BODY_ANCHOR,
            LONG_TEXT_FLAG_BODY,
        ),
        (
            "E65 long-text table update",
            "L_f840067e:",
            LONG_TEXT_TABLE_DISPATCH_ANCHOR,
            LONG_TEXT_TABLE_DISPATCH_LINES,
            LONG_TEXT_TABLE_BODY_ANCHOR,
            LONG_TEXT_TABLE_BODY,
        ),
        (
            "E65 long-text lookup",
            "L_f8400660:",
            LONG_TEXT_LOOKUP_DISPATCH_ANCHOR,
            LONG_TEXT_LOOKUP_DISPATCH_LINES,
            LONG_TEXT_LOOKUP_BODY_ANCHOR,
            LONG_TEXT_LOOKUP_BODY,
        ),
        (
            "E65 long settings lookup",
            "L_f8400c44:",
            LONG_SETTINGS_LOOKUP_DISPATCH_ANCHOR,
            LONG_SETTINGS_LOOKUP_DISPATCH_LINES,
            LONG_SETTINGS_LOOKUP_BODY_ANCHOR,
            LONG_SETTINGS_LOOKUP_BODY,
        ),
        (
            "E65 long settings flag",
            "L_f83fc120:",
            LONG_SETTINGS_FLAG_DISPATCH_ANCHOR,
            LONG_SETTINGS_FLAG_DISPATCH_LINES,
            LONG_SETTINGS_FLAG_BODY_ANCHOR,
            LONG_SETTINGS_FLAG_BODY,
        ),
        (
            "E65 long error table",
            "L_f8400d02:",
            LONG_ERROR_TABLE_DISPATCH_ANCHOR,
            LONG_ERROR_TABLE_DISPATCH_LINES,
            LONG_ERROR_TABLE_BODY_ANCHOR,
            LONG_ERROR_TABLE_BODY,
        ),
        (
            "E65 long-text copy loop",
            "L_f83fcc12:",
            LONG_TEXT_COPY_DISPATCH_ANCHOR,
            LONG_TEXT_COPY_DISPATCH_LINES,
            LONG_TEXT_COPY_BODY_ANCHOR,
            LONG_TEXT_COPY_BODY,
        ),
        (
            "E65 long error assert helper",
            "L_f84071e2:",
            LONG_ERROR_ASSERT_DISPATCH_ANCHOR,
            LONG_ERROR_ASSERT_DISPATCH_LINES,
            LONG_ERROR_ASSERT_BODY_ANCHOR,
            LONG_ERROR_ASSERT_BODY,
        ),
        (
            "E65 long error object",
            "L_f8408cd2:",
            LONG_ERROR_OBJECT_DISPATCH_ANCHOR,
            LONG_ERROR_OBJECT_DISPATCH_LINES,
            LONG_ERROR_OBJECT_BODY_ANCHOR,
            LONG_ERROR_OBJECT_BODY,
        ),
        (
            "E65 second long error object",
            "L_f840863a:",
            LONG_ERROR_SECOND_DISPATCH_ANCHOR,
            LONG_ERROR_SECOND_DISPATCH_LINES,
            LONG_ERROR_SECOND_BODY_ANCHOR,
            LONG_ERROR_SECOND_BODY,
        ),
        (
            "E65 Arabic Latin-text branch",
            "L_f83fe4d8:",
            ARABIC_LATIN_DISPATCH_ANCHOR,
            ARABIC_LATIN_DISPATCH_LINE,
            ARABIC_LATIN_BODY_ANCHOR,
            ARABIC_LATIN_BODY,
        ),
        (
            "E65 Arabic Latin-text ARM branch",
            "L_f83fec32:",
            ARABIC_LATIN_ARM_DISPATCH_ANCHOR,
            ARABIC_LATIN_ARM_DISPATCH_LINE,
            ARABIC_LATIN_ARM_BODY_ANCHOR,
            ARABIC_LATIN_ARM_BODY,
        ),
    )
    changed = False
    for name, sentinel, dispatch_anchor, dispatch_lines, body_anchor, body in patches:
        text, applied = add_patch(
            text,
            name=name,
            sentinel=sentinel,
            dispatch_anchor=dispatch_anchor,
            dispatch_lines=dispatch_lines,
            body_anchor=body_anchor,
            body=body,
        )
        changed |= applied

    with gzip.open(GENERATED_PATCH_DATA, "rt", encoding="utf-8") as stream:
        generated = json.load(stream)
    generated_anchors = {
        "speed_setup": (
            "E65 NVDA speed setup",
            "L_f840049c:",
            "    case 0xf840049au: goto L_f840049a;\n",
            "L_f84005be:\n",
        ),
        "speed_prefix": (
            "E65 NVDA speed prefix",
            "L_f84006b0:",
            "    case 0xf84006aeu: goto L_f84006ae;\n",
            "L_f84006d4:\n",
        ),
        "speed_loop": (
            "E65 NVDA speed loop",
            "L_f84006e8:",
            "    case 0xf84006e6u: goto L_f84006e6;\n",
            "L_f8400754:\n",
        ),
        "speed": (
            "E65 NVDA speed path",
            "L_f840077e:",
            "    case 0xf840077cu: goto L_f840077c;\n",
            "L_f8400818:\n",
        ),
        "speed_tail": (
            "E65 NVDA speed tail",
            "L_f8400830:",
            "    case 0xf840082eu: goto L_f840082e;\n",
            "L_f840084c:\n",
        ),
        "speed_mid": (
            "E65 NVDA speed middle path",
            "L_f8400856:",
            "    case 0xf8400854u: goto L_f8400854;\n",
            "L_f840088c:\n",
        ),
        "helper": (
            "E65 NVDA speed helper",
            "L_f8402d96:",
            "    case 0xf8402ce0u: goto L_f8402ce0;\n",
            "L_f8402da6:\n",
        ),
        "arm": (
            "E65 NVDA speed ARM helper",
            "L_f8403e30:",
            "    case 0xf8403e20u: goto L_f8403e20;\n",
            "L_f8403e38:\n",
        ),
        "speed_epilogue": (
            "E65 NVDA speed epilogue",
            "L_f8400f08:",
            "    case 0xf8400f06u: goto L_f8400f06;\n",
            "L_f8400f0c:\n",
        ),
        "rate_65": (
            "E65 NVDA rate 65 regression",
            "L_f8400a30:",
            "    case 0xf8400a2eu: goto L_f8400a2e;\n",
            "L_f8400a32:\n",
        ),
        "menu_branch": (
            "E65 NVDA menu branch",
            "L_f8400a68:",
            "    case 0xf8400a66u: goto L_f8400a66;\n",
            "L_f8400a72:\n",
        ),
        "rate_65_return": (
            "E65 NVDA rate 65 return",
            "L_f84010ce:",
            "    case 0xf84010ccu: goto L_f84010cc;\n",
            "L_f84010d8:\n",
        ),
        "rate_65_memory": (
            "E65 NVDA rate 65 memory helper",
            "L_f83fecec:",
            "    case 0xf83feceau: goto L_f83fecea;\n",
            "L_f83fecfe:\n",
        ),
        "rate_65_memory_tail": (
            "E65 NVDA rate 65 memory tail",
            "L_f83fedc4:",
            "    case 0xf83fedc2u: goto L_f83fedc2;\n",
            "L_f83fedc8:\n",
        ),
        "rate_65_buffer": (
            "E65 NVDA rate 65 buffer helper",
            "L_f83feeaa:",
            "    case 0xf83feea8u: goto L_f83feea8;\n",
            "L_f83feec6:\n",
        ),
        "pt_delete_thumb": (
            "E65 phrase-tree delete",
            "L_f914e6cc:",
            "    case 0xf914e6cau: goto L_f914e6ca;\n",
            "L_f914e6f8:\n",
        ),
        "pt_delete_vtable": (
            "E65 phrase-tree delete vtable helper",
            "L_f914e85a:",
            "    case 0xf914e858u: goto L_f914e858;\n",
            "L_f914e894:\n",
        ),
        "pt_delete_arm_a": (
            "E65 phrase-tree delete ARM helper A",
            "L_f914eda0:",
            "    case 0xf914ed90u: goto L_f914ed90;\n",
            "L_f914edb0:\n",
        ),
        "pt_delete_arm_b": (
            "E65 phrase-tree delete ARM helper B",
            "L_f914ee28:",
            "    case 0xf914ee08u: goto L_f914ee08;\n",
            "L_f914ee30:\n",
        ),
        "pt_delete_arm_c": (
            "E65 phrase-tree delete ARM helper C",
            "L_f914eda8:",
            "    case 0xf914eda0u: goto L_f914eda0;\n",
            "L_f914edb0:\n",
        ),
        "long_prime": (
            "E65 long-text prime continuation",
            "L_f8406912:",
            "    case 0xf84068e4u: goto L_f84068e4;\n",
            "L_f840693a:\n",
        ),
        "long_word": (
            "E65 long-text word helper",
            "L_f840a876:",
            "    case 0xf840a874u: goto L_f840a874;\n",
            "L_f840aa00:\n",
        ),
        "long_word_bridge": (
            "E65 long-text word helper bridge",
            "L_f840aa10:",
            "    case 0xf840aa0eu: goto L_f840aa0e;\n",
            "L_f840aa1a:\n",
        ),
        "long_word_tail": (
            "E65 long-text word helper tail",
            "L_f840af60:",
            "    case 0xf840af5eu: goto L_f840af5e;\n",
            "L_f840afec:\n",
        ),
        "long_helper": (
            "E65 long-text helper",
            "L_f840ed00:",
            "    case 0xf840ecfeu: goto L_f840ecfe;\n",
            "L_f840ed12:\n",
        ),
        "long_helper_tail": (
            "E65 long-text helper tail",
            "L_f840ee9e:",
            "    case 0xf840ee9cu: goto L_f840ee9c;\n",
            "L_f840efc8:\n",
        ),
        "long_postprocess": (
            "E65 long-text post-processing",
            "L_f840d0d4:",
            "    case 0xf840d0d2u: goto L_f840d0d2;\n",
            "L_f840d0e0:\n",
        ),
        "long_settings_tail": (
            "E65 long-text settings tail",
            "L_f8400438:",
            "    case 0xf8400436u: goto L_f8400436;\n",
            "L_f840043e:\n",
        ),
    }
    if set(generated) != set(generated_anchors):
        raise SystemExit("E65 generated patch data has unexpected sections")
    for key, (name, sentinel, dispatch_anchor, body_anchor) in generated_anchors.items():
        section = generated[key]
        text, applied = add_patch(
            text,
            name=name,
            sentinel=sentinel,
            dispatch_anchor=dispatch_anchor,
            dispatch_lines=section["cases"],
            body_anchor=body_anchor,
            body=section["body"],
        )
        changed |= applied

    if "case 0xf814088cu:" not in text:
        if text.count(RARRAY_CLOSE_ANCHOR) != 1:
            raise SystemExit("E65 RArrayBase::Close anchor is missing or ambiguous")
        text = text.replace(
            RARRAY_CLOSE_ANCHOR,
            RARRAY_CLOSE_ANCHOR + RARRAY_CLOSE_CASE,
            1,
        )
        changed = True
    if "case 0xf812ccc0u:" not in text:
        if text.count(RARRAY_CLOSE_ANCHOR) != 1:
            raise SystemExit("E65 operator delete anchor is missing or ambiguous")
        text = text.replace(
            RARRAY_CLOSE_ANCHOR,
            RARRAY_CLOSE_ANCHOR + OBJECT_FREE_CASE,
            1,
        )
        changed = True

    if changed:
        args.source.write_text(text, encoding="utf-8")
        print("added Nokia E65 regression frontend paths")
    else:
        print("Nokia E65 regression frontend paths are already present")


if __name__ == "__main__":
    main()
