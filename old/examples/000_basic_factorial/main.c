#include <stdio.h>

extern int
main(void)
{
    // Examples are the primary form of documentation for using the Meta-Preprocessor.
    // It is also a form of test suite.
    // Run `cli.py test` to run the Meta-Preprocessor on every example (and have the output verified).
    // If you don't want to or can't, see the `prebuilt` folder for expected output and generated files.

    // Below is an example usage of the Meta-Preprocessor;
    // the first few factorials are computed and a look-up table is generated as C code.

    #include "factorial.h"
    /* #meta
        factorials = []

        for n in range(20):

            product = 1

            for i in range(1, n+1):
                product *= i

            factorials += [product]

        Meta.line(f'''
            static const uint64_t FACTORIAL_LUT[] = {{ {', '.join(map(str, factorials))} }};
        ''')

    */

    int n = 9;

    printf("The value of %d! is %llu", n, FACTORIAL_LUT[n]);
}
