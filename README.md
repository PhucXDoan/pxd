# The PXD Library.

This repository is a set of Python scripts that I've developed over time while working on projects,
but felt like they could be used in many other projects too.
Thus, the PXD library, where PXD is the initials of my name, Phuc Xuan Doan.

As of right now,
the main way to use this library is through git submodules (or the manual downloading of the files).

```
git submodule add https://github.com/PhucXDoan/pxd ./pxd
```
```
git submodule update --init --recursive
```

At some point, PXD will be its own proper PyPi package that can be installed with `pip`.

> [!CAUTION]
> This `README.md` will only provide a basic overview of the functionalities of each module,
> but will not be exhaustive.
> This is far from ideal,
> but this library is highly experimental,
> so breaking changes are expected.
>
> At the end of the day,
> always consult the source code for undescribed features.
> To see this library in practice,
> check out a [project](https://github.com/RockSat-X/RSXVT2026) I'm working on.

- [Meta-Preprecessor](#meta-preprocessor).
- [Log](#log).
- [Utilities](#utilities).
- [S-Expression Parser](#s-expression-parser).





# Meta-Preprocessor.

The meta-preprocessor is used to generate code in a similar way [cog](https://cog.readthedocs.io/en/latest/#) does,
but is specifically designed for the C preprocessor (and thus for C/C++ output).[^cog]

[^cog]: I've never used cog before,
so I can't say anything more about the exact differences
between my meta-preprocessor and Ned Batchelder's cog.

The meta-preprocessor operates on having Python code
embedded in multi-lined comments tagged with `#meta` within C/C++ source code.
For example:

```c
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

The meta-preprocessor will find the comment (to which it now goes by the name *meta-directive*),
run the Python code,
and output the generated code into the file `output.txt`.
Then during compilation,
the C preprocessor will expand the `#include` to arrive at the final output (more or less):

```c
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
we can have one meta-directive export the value of `NAMES` and `C`
and another meta-directive to import them.
The following snippet would produce the sample output for `example.meta`.

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

Variables that are exported out of the meta-directive are listed to the left of the `:`,
while variables that are imported into the meta-directive are listed to the right of the `:`.

This means you can define global data structures and helper functions that other meta-directives can import and use
without having to define anything multiple times.
Thus, the definition of `NAMES` and `C` can be in a completely separate file.

The above example can also be rewritten as so:

```c
#include "example.meta"
/* #meta
    Meta.enums('Name', 'int', NAMES)
    Meta.define('LIGHTSPEED', C)
*/

/* #meta NAMES, C
    NAMES = ['Ralph', 'Phuc', 'Kenny', 'Penny', 'Katelyn']
    C     = 299_792_458
*/
```

This is to show two things:

1. Meta-directives can be evaluated out-of-order.
Thus, just because one meta-directive is higher up in the source file, it doesn't mean it'll be executed first.
The order that the meta-directives are evaluated in is entirely dependent upon their import and export dependencies.

2. If a meta-directive exports and imports nothing (that is, a bare `#meta` tag),
then it'll actually implicitly import everything.
The rationale here is that these "export/import-less" meta-directives
don't actually affect the dependencies of other meta-directives,
so they can be executed last,
and in doing so,
we might as well have those meta-directives be able to access to every exported value.

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

This syntax of exports/imports is perhaps a little confusing at first look, but is quite comfortable to work with.
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

If this meta-directive also generates code,
it'll use the same syntax with `#include`:

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
each depending on each other for different variables,
all spread across the code base, all evaluated in an out-of-order fashion.
Luckily,
the meta-preprocessor wraps all exceptions with `MetaError` which provides
a built-in method to log the error.

<p align="center"><kbd><img src="https://github.com/user-attachments/assets/70acd11f-72f7-475d-a10d-0ebefb53093d" width="600px"></kbd></p>

If you don't like the look of the output,
you can always inspect the exception and make your own diagnostic.





# Log.

The log module extends Python's `print` with some convenience features.

It can be used like a regular `print`.

```python
log('Hello, World!')
# |Hello, World!
```

But it is not a drop-in replacement,
because it does certain things like deindentation.
```python
log(f'''
    Hello,
        World!
        This is a multilined string
            which has space indentation.
            but `log` is accounting for it.
''')
# |Hello,
# |    World!
# |    This is a multilined string
# |        which has space indentation.
# |        but `log` is accounting for it.
```

Another difference is that `log` only uses the first argument for the value to be printed out.
If given multiple arguments,
they are assumed to be for `.format(...)`.
```python
log('My name is {}. I am {} years old.', 'Ralph', 4)
# |My name is Ralph. I am 4 years old.
```

The module also defines `ANSI` to allow for ANSI escape sequences
for coloring the output text and such.
```python
log(ANSI('This text would be red.', 'fg_red'))
log(ANSI('This text would have a red background.', 'bg_red'))
log(ANSI('This text would be bold and green.', 'fg_green', 'bold'))
log(
    f'''
        I am {}
        and she is {}!
    ''',
    ANSI('red and underlined', 'fg_red', 'underline'),
    ANSI('blue and bold', 'fg_blue', 'bold'),
)
```

The `ANSI` helper can also be used as a context-manager to allow for nested properties.
```python
with ANSI('fg_red'):

    log('This text is red.')

    with ANSI('bold'):
        log('This text is red and bold.')
        log(ANSI('This text is green and bold.', 'fg_green'))

    log('This text is now just red.')
```

Another context-manager is `Indent` which by default adds an indentation of four spaces.
```python
log('Hello')

with Indent():

    log('World')

    with Indent():
        log('Bye')

    log('World')

log('!')

# |Hello
# |    World
# |        Bye
# |    World
# |!
```

The indentation can be set to anything;
there's an option to allow for a hanging indent where the characters for the indentation
is only printed once and the rest of the lines will be indented with whitespace of the same length.

```python
with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
    log('Something bad happened!')
    log('This is where I explain it.')
    log('This explanation spans multiple lines.')

# |[ERROR] Something bad happened!
# |        This is where I explain it.
# |        This explanation spans multiple lines.
```





# Utilities.

The infamous utilities module.

This just has helper functions that do very specific things
but are still useful to have in a very general context.

More helper functions might be added,
but the size of this module will always be made small,
so some functions might be completely axed.

The rationale here is that having a large number of helper functions makes it hard to remember them all,
thus they'd be used less often,
defeating the whole point of the utilities module.





# S-Expression Parser.

This module defines a parser for S-expressions.
That's pretty much it.
There are other existing [implementations](https://sexpdata.readthedocs.io/en/latest/#),
but I just wanted something custom-made
that I can soon improve upon to have better error messages and performance.
