# The PXD Library.

This repository is a set of Python scripts that I've developed over time while working on projects,
but felt like they could be also used in a many other projects too.
The initials PXD refers to my name, Phuc Xuan Doan.

As of right now,
the main way to use this library is through git submodules (or manual downloading of files).

```
$ git submodule add https://github.com/PhucXDoan/pxd ./pxd
$ git submodule update --init --recursive
```

At some point, PXD will be its own PyPi package.

## Meta-Preprocessor.

The meta-preprocessor is used to generate code in a similar way [`cog`](https://cog.readthedocs.io/en/latest/#) does,
but is specifically designed for the C preprocessor (and thus for C/C++ output).[^cog]

[^cog]: I've never used `cog`, so I can't say all the exact differences between my meta-preprocessor and Ned Batchelder's `cog`.

This is mostly done through Python code written in multi-lined comments (tagged with `#meta`) embedded within the source code.
For example:

```c
// [main.c] Pre-preprocessing.

int main()
{
    #include "output.txt"
    /* #meta
        for i in range(4):
            Meta.line(f'''
                printf("{i}");
            ''')
    */
}
```

The meta-preprocessor will find the comment (which we call a *meta-directive*),
run the Python code,
and output the generated code into the file `output.txt`.
Then during compilation,
the C preprocessor will expand the `#include` to arrive at the final output (more or less):

```c
// [main.c] Post-preprocessing.

int main()
{
    printf("0");
    printf("1");
    printf("2");
    printf("3");
}
```

The meta-preprocessor is designed to be customizable by the caller,
so in a separate Python script,
you'd invoke `pxd.metapreprocessor.do` with the directory to dump the generated files
and the source files for the meta-preprocessor to comb through.
There are other available options, so see the source code for more information.

```python
import pxd.metapreprocessor

try:
    pxd.metapreprocessor.do(
        output_directory_path = "./metapreprocessor_output",
        source_file_paths     = ["./main.c"],
    )
except pxd.metapreprocessor.MetaError as error:
    error.dump() # The built-in exception logger; you can make your own if you'd like.
```

The meta-preprocessor provides a lot of powerful methods in `Meta` to generate C code that looks nice.
See the source code for more information about how to use the methods.

```c
#include "example.meta"
/* #meta
    NAMES = ['Ralph', 'Phuc', 'Kenny', 'Penny', 'Katelyn']
    Meta.enums('Name', 'int', NAMES)

    C = 299_792_458
    Meta.define('LIGHTSPEED', C)
*/
```

```c
enum Name : int
{
    Name_Ralph,
    Name_Phuc,
    Name_Kenny,
    Name_Penny,
    Name_Katelyn,
};
constexpr int Name_COUNT = 5;
#define LIGHTSPEED 299792458
```

One of the superpowers of the meta-preprocessor is its concept of *dependencies*.
Taking the same example above,
we can have one meta-directive export the value of `NAMES` and `C` and another that's importing them.
Variables that are exported out of the meta-directive are listed to the left of the `:`,
while variables that are imported into the meta-directive are listed to the right of the `:`.
Thus, the following snippet would produce the sample output for `example.meta`.

```c
/* #meta NAMES, C :
    NAMES = ['Ralph', 'Phuc', 'Kenny', 'Penny', 'Katelyn']
    C     = 299_792_458
*/

#include "example.meta"
/* #meta : NAMES, C
    Meta.enums('Name', 'int', NAMES)
    Meta.define('LIGHTSPEED', C)
*/
```

This means you can define global data structures and helper functions that other meta-directives can import and use
without having to define anything multiple times.
This can even mean the value of `NAMES` or `C` is defined by a meta-directive in a completely separate file.

The above example can also be written as so:

```c
#include "example.meta"
/* #meta
    Meta.enums('Name', 'int', NAMES)
    Meta.define('LIGHTSPEED', C)
*/

/* #meta NAMES, C :
    NAMES = ['Ralph', 'Phuc', 'Kenny', 'Penny', 'Katelyn']
    C     = 299_792_458
*/
```

This is to show two things:

1. Meta-directives can be evaluated out-of-order.
Thus, just because one meta-directive is higher up in the source file, it doesn't mean it'll be executed first.
The order that the meta-directives are evaluated in is entirely dependent upon their import and export dependencies.

2. If a meta-directive exports and imports nothing (that is, a bare `#meta` tag),
then it will always be evaluated last alongside with the other meta-directives that also don't export/import anything.
The rationale being here is that these export/import-less meta-directives do not affect the dependencies of other meta-directives,
so they can be executed last,
and in doing so,
we might as well have those meta-directives have access to every exported value.

The different forms of exports/imports is detailed below:

```c
/* #meta

    # We export nothing.
    # We import nothing explicitly but implicitly import A, B, C, D, E, F, X, Y, Z.
    # This would be the 4th or 5th meta-directive to be evaluated.

*/

/* #meta A, B, C

    # We export A, B, C.
    # We import nothing explicitly but implicitly import X, Y, Z.
    # This would be the 2nd meta-directive to be evaluated.

    A = ...
    B = ...
    C = ...

*/

/* #meta D, E, F : A, B, C

    # We export D, E, F.
    # We import A, B, C explicitly and implicitly import X, Y, Z.
    # This would be the 3rd meta-directive to be evaluated.

    D = ...
    E = ...
    F = ...
*/

/* #meta : D, E, F

    # We export nothing.
    # We import D, E, F explicitly and implicitly import X, Y, Z.
    # This would be the 4th or 5th meta-directive to be evaluated.

    # There's little reason to use this kind of meta-directive
    # because `: D, E, F` can be omitted and D, E, F will be
    # implicitly imported anyways.

*/

/* #meta X, Y, Z :

    # We export nothing.
    # We import nothing.
    # This would be the 1st meta-directive to be evaluated.

    # This kind of meta-directive is best for defining global functions/constants
    # because other meta-directives will not have to worry about importing them;
    # the global functions/constants will always be implicitly imported.

    X = ...
    Y = ...
    Z = ...

*/
```

In a drawing:

```
          (#meta X, Y, Z :)

                  |
                  v

           (#meta A, B, C)

                  |
                  v

     (#meta D, E, F : A, B, C)

                 /\
                /  \
               /    \
              v      v

(#meta : D, E, F)   (#meta)
```

This syntax of exports/imports perhaps a little confusing at first look, but is quite comfortable to work with.
Nonetheless,
for pedalogical reasons,
I'll be reworking it for it to be more clear in the future.

In the event that the meta-directive generates code
but the user does not want to `#include` at that spot where the meta-directive is written,
the `#include` directive can be commented out either with a C or C++ styled comment.
This is most useful for when the generated code will be used in multiple places,
but you don't want to make any of those places be the place where the meta-directive defines the file.
```c
// #include "example_1.meta"
/* #meta

    with Meta.enter('if (foobar())'):
        make_body()

*/

/* #include "example_2.meta"
/* #meta

    with Meta.enter('if (foobar())'):
        make_body()

*/
```

When a meta-directive becomes sufficiently large,
it becomes almost like its own entire Python script.
In this event,
a Python file can be made with the first comment being `#meta` to indicate to the meta-preprocessor
that the entire file should be interpreted as a meta-directive.

```python
#meta NAMES, C
NAMES = ['Ralph', 'Phuc', 'Kenny', 'Penny', 'Katelyn']
C     = 299_792_458
```

Meta-directives that also generate code uses the same syntax with `#include`:

```python
#include "stuff.h"
#meta NAMES, C

NAMES = ['Ralph', 'Phuc', 'Kenny', 'Penny', 'Katelyn']
C     = 299_792_458

Meta.enums('Name', 'int', NAMES)
Meta.define('LIGHTSPEED', C)
```

Naturally,
one is concerned with the quality of error messages,
especially when there are multiple meta-directives,
each depending on each other for different variables and what not,
all spread across the code base, all evaluated in an out-of-order fashion.

Luckily,
the meta-preprocessor provides a built-in way to log exceptions that arise
during the evaluation of meta-directives.
Exception that are raised are wrapped by `MetaError` which provides a method to do this.

If you don't like the look of the output,
you can always inspect the exception object and output your own diagnostic.

This section on the meta-preprocessor is not exhaustive.
The meta-preprocessor is very technical and highly experimental,
so please take time to read the source code if you'd like to learn more.