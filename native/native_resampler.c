#include <stdint.h>

/* Compiled for the native ARM64 helper process bundled with the add-on. */

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

static int32_t add32(int32_t a, int32_t b) {
    return (int32_t)((uint32_t)a + (uint32_t)b);
}

static int32_t mul_hi16(int32_t a, int32_t b) {
    uint32_t low = (uint32_t)((int64_t)a * (int64_t)b);
    return ((int32_t)low) >> 16;
}

static void symmetric(int32_t *ring, uint16_t position,
                      const int32_t *coefficients, int32_t sample,
                      uint16_t half, uint16_t length) {
    for (uint32_t i = 0; i < half; ++i) {
        int32_t term = mul_hi16(coefficients[i], sample);
        uint32_t right = position + i;
        if (right >= length) right -= length;
        uint32_t left = position + length - 1u - i;
        if (left >= length) left -= length;
        ring[right] = add32(ring[right], term);
        ring[left] = add32(ring[left], term);
    }
}

API int32_t nokia_resample(
    const int16_t *input, uint32_t sample_count,
    int16_t *output, uint32_t output_capacity,
    int32_t *ring1, int32_t *ring2, int32_t *ring3,
    const int32_t *coeff1, const int32_t *coeff2, const int32_t *coeff3,
    uint16_t length1, uint16_t length2, uint16_t length3,
    uint16_t repeat1, uint16_t repeat2, uint16_t repeat3,
    uint16_t divisor,
    uint16_t *pos1_ptr, uint16_t *pos2_ptr, uint16_t *pos3_ptr,
    uint32_t *phase_ptr) {
    if (!input || !output || !ring1 || !ring2 || !ring3 ||
        !coeff1 || !coeff2 || !coeff3 || !pos1_ptr || !pos2_ptr ||
        !pos3_ptr || !phase_ptr || !length1 || !length2 || !length3 ||
        !divisor) return -1;

    uint16_t pos1 = *pos1_ptr, pos2 = *pos2_ptr, pos3 = *pos3_ptr;
    uint32_t phase = *phase_ptr, produced = 0;
    const uint16_t half1 = length1 / 2;
    const uint16_t half2 = length2 / 2;
    const uint16_t half3 = (length3 - 1) / 2;

    for (uint32_t sample_index = 0; sample_index < sample_count;
         ++sample_index) {
        int32_t sample = input[sample_index];
        symmetric(ring1, pos1, coeff1, sample, half1, length1);
        if (length1 & 1) {
            uint32_t middle = pos1 + half1;
            if (middle >= length1) middle -= length1;
            ring1[middle] = add32(ring1[middle],
                                  mul_hi16(coeff1[half1], sample));
        }

        for (uint32_t first = 0; first < repeat1; ++first) {
            int32_t stage1 = ring1[pos1];
            symmetric(ring2, pos2, coeff2, stage1, half2, length2);

            for (uint32_t second = 0; second < repeat2; ++second) {
                int32_t stage2 = ring2[pos2];
                symmetric(ring3, pos3, coeff3, stage2, half3, length3);
                uint32_t middle = pos3 + half3;
                if (middle >= length3) middle -= length3;
                ring3[middle] = add32(ring3[middle],
                                      mul_hi16(coeff3[half3], stage2));

                for (uint32_t third = 0; third < repeat3; ++third) {
                    if (phase % divisor == 0) {
                        if (produced >= output_capacity) return -2;
                        output[produced++] = (int16_t)ring3[pos3];
                        phase = 0;
                    }
                    ring3[pos3] = 0;
                    if (++pos3 >= length3) pos3 = 0;
                    ++phase;
                }
                ring2[pos2] = 0;
                if (++pos2 >= length2) pos2 = 0;
            }
            ring1[pos1] = 0;
            if (++pos1 >= length1) pos1 = 0;
        }
    }

    *pos1_ptr = pos1;
    *pos2_ptr = pos2;
    *pos3_ptr = pos3;
    *phase_ptr = phase;
    return (int32_t)produced;
}
