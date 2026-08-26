#include <stdint.h>
#include <string.h>

#ifdef _WIN32
#define NOKIA_EXPORT __declspec(dllexport)
#else
#define NOKIA_EXPORT __attribute__((visibility("default")))
#endif

static uint32_t as_bits(int32_t value) {
    uint32_t result;
    memcpy(&result, &value, sizeof(result));
    return result;
}

static int32_t from_bits(uint32_t value) {
    int32_t result;
    memcpy(&result, &value, sizeof(result));
    return result;
}

static int32_t add_wrap(int32_t left, int32_t right) {
    return from_bits(as_bits(left) + as_bits(right));
}

static int32_t mul_low(int32_t left, int32_t right) {
    return from_bits(as_bits(left) * as_bits(right));
}

static int32_t arithmetic_shift_right(int32_t value, unsigned count) {
    uint32_t bits = as_bits(value);
    if (!count) return value;
    if (bits & 0x80000000u)
        bits = (bits >> count) | (~0u << (32u - count));
    else
        bits >>= count;
    return from_bits(bits);
}

NOKIA_EXPORT int32_t nokia_filter_q11(int32_t state[5], int32_t input) {
    int32_t old0 = state[3], old1 = state[4];
    int32_t part2 = arithmetic_shift_right(
        mul_low(arithmetic_shift_right(state[2], 4), old1), 11);
    int32_t part1 = arithmetic_shift_right(
        mul_low(arithmetic_shift_right(state[1], 4), old0), 11);
    int32_t part0 = arithmetic_shift_right(
        mul_low(arithmetic_shift_right(state[0], 4), input), 11);
    int32_t output = add_wrap(add_wrap(part2, part1), part0);
    state[4] = old0;
    state[3] = output;
    return output;
}

NOKIA_EXPORT int32_t nokia_filter_q12(int32_t state[5], int32_t input) {
    int32_t old0 = state[3], old1 = state[4];
    int32_t part0 = mul_low(arithmetic_shift_right(state[0], 3), input);
    int32_t part1 = from_bits(as_bits(
        mul_low(arithmetic_shift_right(state[1], 4), old0)) << 1);
    int32_t part2 = mul_low(arithmetic_shift_right(state[2], 3), old1);
    int32_t output = arithmetic_shift_right(
        add_wrap(add_wrap(part0, part1), part2), 12);
    state[4] = old0;
    state[3] = input;
    return output;
}
