#!/usr/bin/env python3
"""Add Nokia 5500 frontend paths exercised by NVDA regression text."""
from __future__ import annotations

import argparse
from pathlib import Path


DISPATCH_ANCHOR = "    case 0xf8451a14u: goto L_f8451a14;\n"
DISPATCH_LINE = "    case 0xf8451e3eu: goto L_f8451e3e;\n"
BODY_ANCHOR = "}\n\nstatic int nokia_frontend_chunk_21("
BODY = """L_f8451e3e:
    nokia_frontend_last_pc=0xf8451e3eu;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r1 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r1 = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) + (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r1 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_f8451e40;
"""

LONG_TEXT_DISPATCH_ANCHOR = "    case 0xf8453f0cu: goto L_f8453f0c;\n"
LONG_TEXT_DISPATCH_LINES = """    case 0xf8453f0eu: goto L_f8453f0e;
    case 0xf8453f10u: goto L_f8453f10;
"""
LONG_TEXT_BODY_ANCHOR = "L_f8453f12:\n"
LONG_TEXT_BODY = """L_f8453f0e:
    nokia_frontend_last_pc=0xf8453f0eu;
    u_150c00 = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)) + (UINT64_C(54) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_15b500 = ((uint64_t)(nokia_mem_load(&machine, (u_150c00 & UINT64_C(0xffffffff)), 2))) & UINT64_C(0xffff);
    reg_r1 = ((uint64_t)((u_15b500 & UINT64_C(0xffff)))) & UINT64_C(0xffffffff);
    goto L_f8453f10;
L_f8453f10:
    nokia_frontend_last_pc=0xf8453f10u;
    goto L_f8453f14;
"""

ASSERT_HELPER_DISPATCH_ANCHOR = "    case 0xf845a3aau: goto L_f845a3aa;\n"
ASSERT_HELPER_DISPATCH_LINES = """    case 0xf845a3e2u: goto L_f845a3e2;
    case 0xf845a3e4u: goto L_f845a3e4;
    case 0xf845a3e6u: goto L_f845a3e6;
    case 0xf845a3e8u: goto L_f845a3e8;
    case 0xf845a3eau: goto L_f845a3ea;
    case 0xf845a3ecu: goto L_f845a3ec;
    case 0xf845a3f0u: goto L_f845a3f0;
"""
ASSERT_HELPER_BODY_ANCHOR = "L_f845a3f2:\n"
ASSERT_HELPER_BODY = """L_f845a3e2:
    nokia_frontend_last_pc=0xf845a3e2u;
    reg_ZR = ((reg_r0 & UINT64_C(0xffffffff)) == 0);
    goto L_f845a3e4;
L_f845a3e4:
    nokia_frontend_last_pc=0xf845a3e4u;
    reg_mult_addr = reg_sp & UINT64_C(0xffffffff);
    reg_mult_addr = (reg_mult_addr - UINT64_C(4)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, reg_mult_addr, reg_lr, 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    reg_mult_addr = (reg_mult_addr - UINT64_C(4)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, reg_mult_addr, reg_r4, 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    reg_sp = reg_mult_addr;
    goto L_f845a3e6;
L_f845a3e6:
    nokia_frontend_last_pc=0xf845a3e6u;
    if (reg_ZR & UINT64_C(0xff)) goto L_f845a3f0;
    goto L_f845a3e8;
L_f845a3e8:
    nokia_frontend_last_pc=0xf845a3e8u;
    reg_r0 = UINT64_C(18);
    goto L_f845a3ea;
L_f845a3ea:
    nokia_frontend_last_pc=0xf845a3eau;
    reg_r0 = (~reg_r0) & UINT64_C(0xffffffff);
    goto L_f845a3ec;
L_f845a3ec:
    nokia_frontend_last_pc=0xf845a3ecu;
    reg_TB = 0;
    reg_lr = UINT64_C(4165313521);
    reg_pc = UINT64_C(4165346000);
    return NOKIA_FRONTEND_CONTINUE;
L_f845a3f0:
    nokia_frontend_last_pc=0xf845a3f0u;
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

LONG_ERROR_DISPATCH_ANCHOR = "    case 0xf845bed0u: goto L_f845bed0;\n"
LONG_ERROR_DISPATCH_LINES = """    case 0xf845bed2u: goto L_f845bed2;
    case 0xf845bed4u: goto L_f845bed4;
    case 0xf845bed6u: goto L_f845bed6;
    case 0xf845bedau: goto L_f845beda;
    case 0xf845bedcu: goto L_f845bedc;
    case 0xf845bedeu: goto L_f845bede;
    case 0xf845bee0u: goto L_f845bee0;
    case 0xf845bee2u: goto L_f845bee2;
    case 0xf845bee6u: goto L_f845bee6;
    case 0xf845bee8u: goto L_f845bee8;
    case 0xf845beeau: goto L_f845beea;
    case 0xf845beecu: goto L_f845beec;
"""
LONG_ERROR_BODY_ANCHOR = "L_f845beee:\n"
LONG_ERROR_BODY = """L_f845bed2:
    nokia_frontend_last_pc=0xf845bed2u;
    reg_CY = ((reg_r0 & UINT64_C(0x10000000)) != 0);
    reg_r1 = ((reg_r0 & UINT64_C(0xffffffff)) << 4) & UINT64_C(0xffffffff);
    reg_NG = ((reg_r1 & UINT64_C(0x80000000)) != 0);
    reg_ZR = ((reg_r1 & UINT64_C(0xffffffff)) == 0);
    goto L_f845bed4;
L_f845bed4:
    nokia_frontend_last_pc=0xf845bed4u;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150a00, 4) & UINT64_C(0xffffffff);
    goto L_f845bed6;
L_f845bed6:
    nokia_frontend_last_pc=0xf845bed6u;
    reg_TB = 1;
    reg_lr = UINT64_C(4165320411);
    reg_pc = UINT64_C(4165313560);
    return NOKIA_FRONTEND_CONTINUE;
L_f845beda:
    nokia_frontend_last_pc=0xf845bedau;
    reg_r5 = reg_r0 & UINT64_C(0xffffffff);
    reg_ZR = (reg_r5 == 0);
    reg_NG = ((reg_r5 & UINT64_C(0x80000000)) != 0);
    goto L_f845bedc;
L_f845bedc:
    nokia_frontend_last_pc=0xf845bedcu;
    if (!(reg_ZR & UINT64_C(0xff))) goto L_f845bee6;
    goto L_f845bede;
L_f845bede:
    nokia_frontend_last_pc=0xf845bedeu;
    reg_r0 = 1;
    goto L_f845bee0;
L_f845bee0:
    nokia_frontend_last_pc=0xf845bee0u;
    reg_r1 = UINT64_C(4165320988);
    goto L_f845bee2;
L_f845bee2:
    nokia_frontend_last_pc=0xf845bee2u;
    reg_TB = 1;
    reg_lr = UINT64_C(4165320423);
    reg_pc = UINT64_C(4165313506);
    return NOKIA_FRONTEND_CONTINUE;
L_f845bee6:
    nokia_frontend_last_pc=0xf845bee6u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f845bee8;
L_f845bee8:
    nokia_frontend_last_pc=0xf845bee8u;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) << 1) & UINT64_C(0xffffffff);
    goto L_f845beea;
L_f845beea:
    nokia_frontend_last_pc=0xf845beeau;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150c00, reg_r0 & UINT64_C(0xffff), 2)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f845beec;
L_f845beec:
    nokia_frontend_last_pc=0xf845beecu;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150a00, reg_r5 & UINT64_C(0xffffffff), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f845beee;
"""

LONG_ERROR_SECOND_DISPATCH_ANCHOR = "    case 0xf845b838u: goto L_f845b838;\n"
LONG_ERROR_SECOND_DISPATCH_LINES = """    case 0xf845b83au: goto L_f845b83a;
    case 0xf845b83cu: goto L_f845b83c;
    case 0xf845b83eu: goto L_f845b83e;
    case 0xf845b842u: goto L_f845b842;
    case 0xf845b844u: goto L_f845b844;
    case 0xf845b846u: goto L_f845b846;
    case 0xf845b848u: goto L_f845b848;
    case 0xf845b84au: goto L_f845b84a;
    case 0xf845b84eu: goto L_f845b84e;
    case 0xf845b850u: goto L_f845b850;
    case 0xf845b852u: goto L_f845b852;
    case 0xf845b854u: goto L_f845b854;
"""
LONG_ERROR_SECOND_BODY_ANCHOR = "L_f845b856:\n"
LONG_ERROR_SECOND_BODY = """L_f845b83a:
    nokia_frontend_last_pc=0xf845b83au;
    reg_CY = ((reg_r0 & UINT64_C(0x10000000)) != 0);
    reg_r1 = ((reg_r0 & UINT64_C(0xffffffff)) << 4) & UINT64_C(0xffffffff);
    reg_NG = ((reg_r1 & UINT64_C(0x80000000)) != 0);
    reg_ZR = ((reg_r1 & UINT64_C(0xffffffff)) == 0);
    goto L_f845b83c;
L_f845b83c:
    nokia_frontend_last_pc=0xf845b83cu;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150a00, 4) & UINT64_C(0xffffffff);
    goto L_f845b83e;
L_f845b83e:
    nokia_frontend_last_pc=0xf845b83eu;
    reg_TB = 1;
    reg_lr = UINT64_C(4165318723);
    reg_pc = UINT64_C(4165313560);
    return NOKIA_FRONTEND_CONTINUE;
L_f845b842:
    nokia_frontend_last_pc=0xf845b842u;
    reg_r5 = reg_r0 & UINT64_C(0xffffffff);
    reg_ZR = (reg_r5 == 0);
    reg_NG = ((reg_r5 & UINT64_C(0x80000000)) != 0);
    goto L_f845b844;
L_f845b844:
    nokia_frontend_last_pc=0xf845b844u;
    if (!(reg_ZR & UINT64_C(0xff))) goto L_f845b84e;
    goto L_f845b846;
L_f845b846:
    nokia_frontend_last_pc=0xf845b846u;
    reg_r0 = 1;
    goto L_f845b848;
L_f845b848:
    nokia_frontend_last_pc=0xf845b848u;
    reg_r1 = UINT64_C(4165318948);
    goto L_f845b84a;
L_f845b84a:
    nokia_frontend_last_pc=0xf845b84au;
    reg_TB = 1;
    reg_lr = UINT64_C(4165318735);
    reg_pc = UINT64_C(4165313506);
    return NOKIA_FRONTEND_CONTINUE;
L_f845b84e:
    nokia_frontend_last_pc=0xf845b84eu;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    reg_r0 = nokia_mem_load(&machine, u_150c00, 2) & UINT64_C(0xffff);
    goto L_f845b850;
L_f845b850:
    nokia_frontend_last_pc=0xf845b850u;
    reg_r0 = ((reg_r0 & UINT64_C(0xffffffff)) << 1) & UINT64_C(0xffffffff);
    goto L_f845b852;
L_f845b852:
    nokia_frontend_last_pc=0xf845b852u;
    u_150c00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(8)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150c00, reg_r0 & UINT64_C(0xffff), 2)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f845b854;
L_f845b854:
    nokia_frontend_last_pc=0xf845b854u;
    u_150a00 = ((reg_r4 & UINT64_C(0xffffffff)) + UINT64_C(12)) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, u_150a00, reg_r5 & UINT64_C(0xffffffff), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_f845b856;
"""

ARABIC_LATIN_DISPATCH_ANCHOR = (
    "    case 0xf84516e2u: goto L_f84516e2;\n"
)
ARABIC_LATIN_DISPATCH_LINE = (
    "    case 0xf84516e4u: goto L_f84516e4;\n"
)
ARABIC_LATIN_BODY_ANCHOR = "L_f84516ee:\n"
ARABIC_LATIN_BODY = """L_f84516e4:
    nokia_frontend_last_pc=0xf84516e4u;
    goto L_f84516ee;
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")
    changed = False
    patches = (
        (
            "L_f8451e3e:",
            "5500 $SysReset",
            DISPATCH_ANCHOR,
            DISPATCH_LINE,
            BODY_ANCHOR,
            BODY,
        ),
        (
            "L_f8453f0e:",
            "5500 long-text path",
            LONG_TEXT_DISPATCH_ANCHOR,
            LONG_TEXT_DISPATCH_LINES,
            LONG_TEXT_BODY_ANCHOR,
            LONG_TEXT_BODY,
        ),
        (
            "L_f845a3e2:",
            "5500 assert helper",
            ASSERT_HELPER_DISPATCH_ANCHOR,
            ASSERT_HELPER_DISPATCH_LINES,
            ASSERT_HELPER_BODY_ANCHOR,
            ASSERT_HELPER_BODY,
        ),
        (
            "L_f845bed2:",
            "5500 long error path",
            LONG_ERROR_DISPATCH_ANCHOR,
            LONG_ERROR_DISPATCH_LINES,
            LONG_ERROR_BODY_ANCHOR,
            LONG_ERROR_BODY,
        ),
        (
            "L_f845b83a:",
            "5500 second long error path",
            LONG_ERROR_SECOND_DISPATCH_ANCHOR,
            LONG_ERROR_SECOND_DISPATCH_LINES,
            LONG_ERROR_SECOND_BODY_ANCHOR,
            LONG_ERROR_SECOND_BODY,
        ),
        (
            "L_f84516e4:",
            "5500 Arabic Latin-text branch",
            ARABIC_LATIN_DISPATCH_ANCHOR,
            ARABIC_LATIN_DISPATCH_LINE,
            ARABIC_LATIN_BODY_ANCHOR,
            ARABIC_LATIN_BODY,
        ),
    )
    for sentinel, name, dispatch_anchor, dispatch_lines, body_anchor, body in patches:
        if sentinel in text:
            continue
        if text.count(dispatch_anchor) != 1:
            raise SystemExit(f"{name} dispatch anchor is missing or ambiguous")
        if text.count(body_anchor) != 1:
            raise SystemExit(f"{name} body anchor is missing or ambiguous")
        text = text.replace(dispatch_anchor, dispatch_anchor + dispatch_lines, 1)
        text = text.replace(body_anchor, body + body_anchor, 1)
        changed = True
    if changed:
        args.source.write_text(text, encoding="utf-8")
        print("added Nokia 5500 regression frontend paths")
    else:
        print("Nokia 5500 regression frontend paths are already present")


if __name__ == "__main__":
    main()
