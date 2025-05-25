#include <stdio.h>

extern int
main(void)
{
    // Below is the same factorial LUT generation script but each entry is now on its own line
    // instead of the entire thing being a single line. The Meta-Preprocessor has a lot of helper
    // functions to make code generation easier and the output highly readable. In this example,
    // indentation is handled automatically with `Meta.enter`, and the opening/closing braces are
    // determined automatically too.

    #include "factorial.h"
    /* #meta
        factorials = []

        for n in range(20):

            product = 1

            for i in range(1, n+1):
                product *= i

            factorials += [product]

        with Meta.enter('static const uint64_t FACTORIAL_LUT[] ='):
            Meta.line(f'{x},' for x in factorials)
    */

    int n = 9;

    printf("The value of %d! is %llu", n, FACTORIAL_LUT[n]);
}
