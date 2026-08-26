#include <stdint.h>
#include <stdio.h>
#include <string.h>

int32_t nokia_filter_q11(int32_t state[5], int32_t input);
int32_t nokia_filter_q12(int32_t state[5], int32_t input);

int main(void) {
    int32_t a[5] = {32767, -12345, 23456, -34567, 45678};
    int32_t b[5];
    memcpy(b, a, sizeof(a));
    int32_t x = -2345;
    int32_t y1 = nokia_filter_q11(a, x);
    int32_t y2 = nokia_filter_q12(b, x);
    printf("%d %d %d %d %d %d\n", y1, a[3], a[4],
           y2, b[3], b[4]);
    return !(y1 == 43383 && a[3] == 43383 && a[4] == -34567
             && y2 == 43382 && b[3] == -2345 && b[4] == -34567);
}
