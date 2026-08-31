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

old_lower_exit_case = "    case 0x830ecbc4u: goto L_830ecbc4;\n"
new_lower_exit_case = """    case 0x830ecbc2u: goto L_830ecbc2;
    case 0x830ecbc4u: goto L_830ecbc4;
"""
if source.count(old_lower_exit_case) != 1:
	raise SystemExit("missing or ambiguous 0x830ecbc2 dispatch marker")
source = source.replace(old_lower_exit_case, new_lower_exit_case, 1)

old_lower_exit_branch = """L_830ecc90:
    nokia_frontend_last_pc=0x830ecc90u;
    u_133e00 = ((uint64_t)(!(reg_CY & UINT64_C(0xff)))) & UINT64_C(0xff);
    u_134000 = ((uint64_t)((u_133e00 & UINT64_C(0xff)) || (reg_ZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_134000 & UINT64_C(0xff))) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_830ecc92;
"""
new_lower_exit_branch = """L_830ecc90:
    nokia_frontend_last_pc=0x830ecc90u;
    u_133e00 = ((uint64_t)(!(reg_CY & UINT64_C(0xff)))) & UINT64_C(0xff);
    u_134000 = ((uint64_t)((u_133e00 & UINT64_C(0xff)) || (reg_ZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_134000 & UINT64_C(0xff))) goto L_830ecbc2;
    goto L_830ecc92;
"""
if source.count(old_lower_exit_branch) != 1:
	raise SystemExit("missing or ambiguous 0x830ecc90 branch marker")
source = source.replace(old_lower_exit_branch, new_lower_exit_branch, 1)

old_lower_exit_target = "L_830ecbc4:\n"
new_lower_exit_target = """L_830ecbc2:
    nokia_frontend_last_pc=0x830ecbc2u;
    goto L_830ecda2;
L_830ecbc4:
"""
if source.count(old_lower_exit_target) != 1:
	raise SystemExit("missing or ambiguous 0x830ecbc2 target marker")
source = source.replace(old_lower_exit_target, new_lower_exit_target, 1)

old_variant_case = """    case 0x830dbbceu: goto L_830dbbce;
    case 0x830dbbeeu: goto L_830dbbee;
"""
new_variant_case = """    case 0x830dbbceu: goto L_830dbbce;
    case 0x830dbbd0u: goto L_830dbbd0;
    case 0x830dbbd2u: goto L_830dbbd2;
    case 0x830dbbd4u: goto L_830dbbd4;
    case 0x830dbbd6u: goto L_830dbbd6;
    case 0x830dbbd8u: goto L_830dbbd8;
    case 0x830dbbdau: goto L_830dbbda;
    case 0x830dbbdcu: goto L_830dbbdc;
    case 0x830dbbe0u: goto L_830dbbe0;
    case 0x830dbbe2u: goto L_830dbbe2;
    case 0x830dbbe4u: goto L_830dbbe4;
    case 0x830dbbe6u: goto L_830dbbe6;
    case 0x830dbbe8u: goto L_830dbbe8;
    case 0x830dbbeau: goto L_830dbbea;
    case 0x830dbbecu: goto L_830dbbec;
    case 0x830dbbeeu: goto L_830dbbee;
"""
if source.count(old_variant_case) != 1:
	raise SystemExit("missing or ambiguous 0x830dbbd0 dispatch marker")
source = source.replace(old_variant_case, new_variant_case, 1)

old_variant_branch = """L_830dbbba:
    nokia_frontend_last_pc=0x830dbbbau;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_830dbbbc;
"""
new_variant_branch = """L_830dbbba:
    nokia_frontend_last_pc=0x830dbbbau;
    u_132e00 = ((uint64_t)((reg_ZR & UINT64_C(0xff)) == (UINT64_C(0) & UINT64_C(0xff)))) & UINT64_C(0xff);
    if ((u_132e00 & UINT64_C(0xff))) goto L_830dbbd0;
    goto L_830dbbbc;
"""
if source.count(old_variant_branch) != 1:
	raise SystemExit("missing or ambiguous 0x830dbbba branch marker")
source = source.replace(old_variant_branch, new_variant_branch, 1)

old_variant_target = "L_830dbbee:\n"
new_variant_target = """L_830dbbd0:
    nokia_frontend_last_pc=0x830dbbd0u;
    u_150a00 = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)) + (UINT64_C(32) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r1 = ((uint64_t)(nokia_mem_load(&machine, (u_150a00 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_830dbbd2;
L_830dbbd2:
    nokia_frontend_last_pc=0x830dbbd2u;
    reg_tmpCY = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) <= (reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r0 & UINT64_C(0xffffffff)), (reg_r1 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) - (reg_r1 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbd4;
L_830dbbd4:
    nokia_frontend_last_pc=0x830dbbd4u;
    u_163100 = ((uint64_t)((UINT64_C(13) & UINT64_C(0xffffffff)) - (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_163200 = ((uint64_t)(nokia_shl((reg_r0 & UINT64_C(0xffffffff)), (u_163100 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    u_163400 = ((uint64_t)((u_163200 & UINT64_C(0xffffffff)) & (UINT64_C(2147483648) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_163500 = ((uint64_t)((UINT64_C(13) & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    u_163600 = ((uint64_t)((u_163500 & UINT64_C(0xff)) && (reg_CY & UINT64_C(0xff)))) & UINT64_C(0xff);
    u_163700 = ((uint64_t)((UINT64_C(13) & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    u_163800 = ((uint64_t)((u_163400 & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    u_163900 = ((uint64_t)((u_163700 & UINT64_C(0xff)) && (u_163800 & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_tmpCY = ((uint64_t)((u_163600 & UINT64_C(0xff)) || (u_163900 & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)(nokia_shl((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(13) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbd6;
L_830dbbd6:
    nokia_frontend_last_pc=0x830dbbd6u;
    u_164a00 = ((uint64_t)((UINT64_C(16) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_163f00 = ((uint64_t)((u_164a00 & UINT64_C(0xffffffff)) - (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_164000 = ((uint64_t)(nokia_shr((reg_r0 & UINT64_C(0xffffffff)), (u_163f00 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    u_164200 = ((uint64_t)((u_164000 & UINT64_C(0xffffffff)) & (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_164300 = ((uint64_t)((u_164a00 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    u_164400 = ((uint64_t)((u_164300 & UINT64_C(0xff)) && (reg_CY & UINT64_C(0xff)))) & UINT64_C(0xff);
    u_164500 = ((uint64_t)((u_164a00 & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    u_164600 = ((uint64_t)((u_164200 & UINT64_C(0xffffffff)) != (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    u_164700 = ((uint64_t)((u_164500 & UINT64_C(0xff)) && (u_164600 & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_tmpCY = ((uint64_t)((u_164400 & UINT64_C(0xff)) || (u_164700 & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_r1 = ((uint64_t)(nokia_shr((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(16) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r1 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r1 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbd8;
L_830dbbd8:
    nokia_frontend_last_pc=0x830dbbd8u;
    reg_r0 = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbda;
L_830dbbda:
    nokia_frontend_last_pc=0x830dbbdau;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(16) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(16) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (UINT64_C(16) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbdc;
L_830dbbdc:
    nokia_frontend_last_pc=0x830dbbdcu;
    reg_lr = ((uint64_t)((UINT64_C(2198715360) & UINT64_C(0xffffffff)) | (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_TB = ((uint64_t)((UINT64_C(1) & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_lr = UINT64_C(2198715361);
    reg_pc=UINT64_C(2198717090); return NOKIA_FRONTEND_CONTINUE;
L_830dbbe0:
    nokia_frontend_last_pc=0x830dbbe0u;
    reg_r4 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r4 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r4 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbe2;
L_830dbbe2:
    nokia_frontend_last_pc=0x830dbbe2u;
    reg_r3 = ((uint64_t)((reg_sp & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    goto L_830dbbe4;
L_830dbbe4:
    nokia_frontend_last_pc=0x830dbbe4u;
    u_150c00 = ((uint64_t)((reg_r3 & UINT64_C(0xffffffff)) + (UINT64_C(8) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    u_15b500 = ((uint64_t)(nokia_mem_load(&machine, (u_150c00 & UINT64_C(0xffffffff)), 2))) & UINT64_C(0xffff);
    reg_r1 = ((uint64_t)((u_15b500 & UINT64_C(0xffff)))) & UINT64_C(0xffffffff);
    goto L_830dbbe6;
L_830dbbe6:
    nokia_frontend_last_pc=0x830dbbe6u;
    u_150a00 = ((uint64_t)((reg_r6 & UINT64_C(0xffffffff)) + (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_r0 = ((uint64_t)(nokia_mem_load(&machine, (u_150a00 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xffffffff);
    goto L_830dbbe8;
L_830dbbe8:
    nokia_frontend_last_pc=0x830dbbe8u;
    reg_tmpCY = ((uint64_t)(nokia_carry((reg_r0 & UINT64_C(0xffffffff)), (reg_r1 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_scarry((reg_r0 & UINT64_C(0xffffffff)), (reg_r1 & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) + (reg_r1 & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbea;
L_830dbbea:
    nokia_frontend_last_pc=0x830dbbeau;
    reg_tmpCY = ((uint64_t)((UINT64_C(1) & UINT64_C(0xffffffff)) <= (reg_r0 & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_tmpOV = ((uint64_t)(nokia_sborrow((reg_r0 & UINT64_C(0xffffffff)), (UINT64_C(1) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_r0 = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) - (UINT64_C(1) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    reg_tmpNG = ((uint64_t)(nokia_sext((reg_r0 & UINT64_C(0xffffffff)), 4) < nokia_sext((UINT64_C(0) & UINT64_C(0xffffffff)), 4))) & UINT64_C(0xff);
    reg_tmpZR = ((uint64_t)((reg_r0 & UINT64_C(0xffffffff)) == (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xff);
    reg_CY = ((uint64_t)((reg_tmpCY & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_ZR = ((uint64_t)((reg_tmpZR & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_NG = ((uint64_t)((reg_tmpNG & UINT64_C(0xff)))) & UINT64_C(0xff);
    reg_OV = ((uint64_t)((reg_tmpOV & UINT64_C(0xff)))) & UINT64_C(0xff);
    goto L_830dbbec;
L_830dbbec:
    nokia_frontend_last_pc=0x830dbbecu;
    u_150a00 = ((uint64_t)((reg_r6 & UINT64_C(0xffffffff)) + (UINT64_C(0) & UINT64_C(0xffffffff)))) & UINT64_C(0xffffffff);
    if (!nokia_mem_store(&machine, (u_150a00 & UINT64_C(0xffffffff)), (reg_r0 & UINT64_C(0xffffffff)), 4)) return NOKIA_FRONTEND_UNSUPPORTED;
    goto L_830dbbee;
L_830dbbee:
"""
if source.count(old_variant_target) != 1:
	raise SystemExit("missing or ambiguous 0x830dbbd0 target marker")
source = source.replace(old_variant_target, new_variant_target, 1)

path.write_text(source, encoding="utf-8", newline="\n")
