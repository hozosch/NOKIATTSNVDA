"""Add lightweight last-call diagnostics to the standalone native runtime."""

from pathlib import Path
import sys


path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
marker = "static int native_call(NokiaRuntime *r, uint32_t entry,"
if marker not in source:
	raise SystemExit("native_call marker not found")

diagnostics = """static uint32_t nokia_runtime_last_entry_value_storage;
static uint32_t nokia_runtime_last_stage_value_storage;
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_last_entry_value(void){return nokia_runtime_last_entry_value_storage;}
NOKIA_RUNTIME_EXPORT uint32_t nokia_runtime_last_stage_value(void){return nokia_runtime_last_stage_value_storage;}

"""
source = source.replace(marker, diagnostics + marker, 1)

old = """    uint32_t regs[17] = {0}, i, sp = STACK_BASE + STACK_SIZE - 0x1000u;
    int status;
"""
new = """    uint32_t regs[17] = {0}, i, sp = STACK_BASE + STACK_SIZE - 0x1000u;
    int status;
    nokia_runtime_last_entry_value_storage=entry;
    if(entry==r->seg_set_style_id)nokia_runtime_last_stage_value_storage=1u;
    else if(entry==r->seg_set_text_ptr)nokia_runtime_last_stage_value_storage=2u;
    else if(entry==r->pt_add_segment)nokia_runtime_last_stage_value_storage=3u;
    else if(entry==r->pt_new)nokia_runtime_last_stage_value_storage=4u;
    else if(entry==r->dev_prime)nokia_runtime_last_stage_value_storage=5u;
    else if(entry==r->dev_synthesize)nokia_runtime_last_stage_value_storage=6u;
    else if(entry==r->dev_buffer_processed)nokia_runtime_last_stage_value_storage=7u;
    else if(entry==r->run_if_ready)nokia_runtime_last_stage_value_storage=8u;
    else if(entry==r->dev_stop)nokia_runtime_last_stage_value_storage=9u;
    else if(entry==r->pt_delete)nokia_runtime_last_stage_value_storage=10u;
    else if(entry==r->cleanup_next)nokia_runtime_last_stage_value_storage=11u;
    else if(entry==r->cleanup_pop)nokia_runtime_last_stage_value_storage=12u;
    else if(entry==r->cleanup_prev)nokia_runtime_last_stage_value_storage=13u;
    else nokia_runtime_last_stage_value_storage=255u;
"""
if old not in source:
	raise SystemExit("native_call body marker not found")
source = source.replace(old, new, 1)
path.write_text(source, encoding="utf-8", newline="\n")

