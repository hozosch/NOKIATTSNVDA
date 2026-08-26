"""Exercise Unicorn's C ABI from the target-architecture Python runtime."""
import ctypes
import sys

dll = ctypes.CDLL(sys.argv[1])
handle = ctypes.c_void_p()

dll.uc_open.argtypes = (ctypes.c_int, ctypes.c_int,
                        ctypes.POINTER(ctypes.c_void_p))
dll.uc_open.restype = ctypes.c_int
dll.uc_mem_map.argtypes = (ctypes.c_void_p, ctypes.c_uint64,
                           ctypes.c_size_t, ctypes.c_uint32)
dll.uc_mem_map.restype = ctypes.c_int
dll.uc_mem_write.argtypes = (ctypes.c_void_p, ctypes.c_uint64,
                             ctypes.c_void_p, ctypes.c_size_t)
dll.uc_mem_write.restype = ctypes.c_int
dll.uc_mem_read.argtypes = (ctypes.c_void_p, ctypes.c_uint64,
                            ctypes.c_void_p, ctypes.c_size_t)
dll.uc_mem_read.restype = ctypes.c_int
dll.uc_close.argtypes = (ctypes.c_void_p,)
dll.uc_close.restype = ctypes.c_int

def check(operation, status):
    if status:
        raise RuntimeError(f'{operation} returned Unicorn error {status}')

check('uc_open', dll.uc_open(1, 0, ctypes.byref(handle)))
if not handle.value:
    raise RuntimeError('uc_open returned a null handle')
try:
    check('uc_mem_map', dll.uc_mem_map(handle, 0x1000, 0x1000, 7))
    source = ctypes.create_string_buffer(b'ARM64 ABI smoke test')
    check('uc_mem_write', dll.uc_mem_write(handle, 0x1000, source,
                                           len(source.raw)))
    result = ctypes.create_string_buffer(len(source.raw))
    check('uc_mem_read', dll.uc_mem_read(handle, 0x1000, result,
                                         len(result.raw)))
    if result.raw != source.raw:
        raise RuntimeError('Unicorn memory round trip did not match')
finally:
    check('uc_close', dll.uc_close(handle))

print(f'ctypes smoke test passed with {sys.version}')
