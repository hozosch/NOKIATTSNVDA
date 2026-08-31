"""Restore proven Nokia 5320 AOT fallthroughs omitted by the trace corpus."""

from pathlib import Path
import sys


path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")

old_cases = """    case 0x830ea396u: goto L_830ea396;
    case 0x830ea39cu: goto L_830ea39c;
"""
new_cases = """    case 0x830ea396u: goto L_830ea396;
    case 0x830ea398u: goto L_830ea398;
    case 0x830ea39au: goto L_830ea39a;
    case 0x830ea39cu: goto L_830ea39c;
"""
if source.count(old_cases) != 1:
	raise SystemExit("missing or ambiguous 0x830ea398 dispatch marker")
source = source.replace(old_cases, new_cases, 1)

old_path = """L_830ea396:
    nokia_frontend_last_pc=0x830ea396u;
    u_132c00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) != (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132c00 & UINT64_C(0xff))) goto L_830ea2c2;
    return NOKIA_FRONTEND_UNSUPPORTED;
L_830ea39c:
"""
new_path = """L_830ea396:
    nokia_frontend_last_pc=0x830ea396u;
    u_132c00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) != (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132c00 & UINT64_C(0xff))) goto L_830ea2c2;
    goto L_830ea398;
L_830ea398:
    nokia_frontend_last_pc=0x830ea398u;
    u_151300 = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)) + (UINT64_C(284) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r0 = ((uint64_t)(nokia_mem_load(&machine, (u_151300 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_830ea39a;
L_830ea39a:
    nokia_frontend_last_pc=0x830ea39au;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830ea39c;
L_830ea39c:
"""
if source.count(old_path) != 1:
	raise SystemExit("missing or ambiguous 0x830ea396 fallthrough marker")
source = source.replace(old_path, new_path, 1)

old_yield_case = """    case 0x830ea3ceu: goto L_830ea3ce;
    case 0x830ea3d2u: goto L_830ea3d2;
"""
new_yield_case = """    case 0x830ea3ceu: goto L_830ea3ce;
    case 0x830ea3d0u: goto L_830ea3d0;
    case 0x830ea3d2u: goto L_830ea3d2;
"""
if source.count(old_yield_case) != 1:
	raise SystemExit("missing or ambiguous 0x830ea3d0 dispatch marker")
source = source.replace(old_yield_case, new_yield_case, 1)

old_yield_target = """L_830ea3d2:
"""
new_yield_target = """L_830ea3d0:
    nokia_frontend_last_pc=0x830ea3d0u;
    goto L_830ea1aa;
L_830ea3d2:
"""
if source.count(old_yield_target) != 1:
	raise SystemExit("missing or ambiguous 0x830ea3d0 branch marker")
source = source.replace(old_yield_target, new_yield_target, 1)


old_loop_case = "    case 0x830eccd0u: goto L_830eccd0;\n"
new_loop_case = """    case 0x830eccd0u: goto L_830eccd0;
    case 0x830eccd2u: goto L_830eccd2;
    case 0x830eccd4u: goto L_830eccd4;
    case 0x830eccd6u: goto L_830eccd6;
    case 0x830eccd8u: goto L_830eccd8;
"""
if source.count(old_loop_case) != 1:
	raise SystemExit("missing or ambiguous 0x830eccd2 dispatch marker")
source = source.replace(old_loop_case, new_loop_case, 1)

old_loop_path = """L_830eccd0:
    nokia_frontend_last_pc=0x830eccd0u;
    u_132c00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) != (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132c00 & UINT64_C(0xff))) goto L_830ecda2;
    return NOKIA_FRONTEND_UNSUPPORTED;
L_830eccda:
"""
new_loop_path = """L_830eccd0:
    nokia_frontend_last_pc=0x830eccd0u;
    u_132c00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) != (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132c00 & UINT64_C(0xff))) goto L_830ecda2;
    goto L_830eccd2;
L_830eccd2:
    nokia_frontend_last_pc=0x830eccd2u;
    u_151300 = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)) + (UINT64_C(284) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r7 = ((uint64_t)(nokia_mem_load(&machine, (u_151300 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_830eccd4;
L_830eccd4:
    nokia_frontend_last_pc=0x830eccd4u;
    reg_r4 = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)) + (reg_r12 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    goto L_830eccd6;
L_830eccd6:
    nokia_frontend_last_pc=0x830eccd6u;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r7 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r7 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r7 = ((uint64_t)((reg_r7 & UINT64_C(0xffffffff)) + (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r7 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r7 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830eccd8;
L_830eccd8:
    nokia_frontend_last_pc=0x830eccd8u;
    goto L_830ecc84;
L_830eccda:
"""
if source.count(old_loop_path) != 1:
	raise SystemExit("missing or ambiguous 0x830eccd2 fallthrough marker")
source = source.replace(old_loop_path, new_loop_path, 1)

path.write_text(source, encoding="utf-8", newline="\n")
