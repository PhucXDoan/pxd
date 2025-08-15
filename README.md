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
- [UI](#ui).
- [Cite](#cite).
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
each depending on each other for different variables and what not,
all spread across the code base, all evaluated in an out-of-order fashion.

Luckily,
the meta-preprocessor provides a built-in way to log exceptions that arise
during the evaluation of meta-directives.
Exception that are raised are wrapped by `MetaError` which provides a method to do this.

<p align="center"><kbd><img src="https://github.com/user-attachments/assets/70acd11f-72f7-475d-a10d-0ebefb53093d" width="600px"></kbd></p>

If you don't like the look of the output,
you can always inspect the exception object and output your own diagnostic.





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
    log('This explaination spans multiple lines.')

# |[ERROR] Something bad happened!
# |        This is where I explain it.
# |        This explaination spans multiple lines.
```





# UI.

The UI module allows for the easy creation of command-line interfaces using Python.

To make one,
create a UI instance by providing a name and description.

```python
import pxd.ui
MyCLI = pxd.ui.UI('MyCLI', 'My command line interface.')
```

This UI instance can be used as a decorator on functions;
these functions you decorate (which I call *verbs*) will be a part of the CLI.

```python
@MyCLI(
    {
        'description' : 'Say hello to the user.',
    },
)
def greet(parameters):
    print('Hello!')

@MyCLI(
    {
        'description' : 'Say bye to the user.',
    },
)
def bye(parameters):
    print('Bye bye!')
```

Invoking the CLI is typically done like so:

```python
import sys
MyCLI.invoke(sys.argv[1:])
```

Thus,
when the user runs the Python script,
the UI module will automatically parse the provided command line arguments
to determine which verb to run.

```
$ ./script.py greet
Hello!

$ ./script.py bye
Bye bye!
```

The UI module has many options to allow for arguments to be passed to the verbs.

```python
@MyCLI(
    {
        'description' : 'Subtracts two numbers.',
    },
    {
        'name'        : 'first',
        'type'        : int,
        'description' : 'The first number on the left-hand side.'
    },
    {
        'name'        : 'second',
        'type'        : int,
        'description' : 'The second number on the right-hand side.'
    },
)
def subtract(parameters):
    print(f'The difference is {parameters.first - parameters.second}.')

MyCLI.invoke(['subtract', '3', '5'])
# |The difference is -2.
```

```python
@MyCLI(
    {
        'description' : 'Say hello to the user.',
    },
    {
        'name'        : 'username',
        'type'        : str,
        'description' : 'Name of the user.'
        'default'     : 'Ralph',
    },
    {
        'name'        : 'uppercase',
        'type'        : bool,
        'description' : 'Output in upper case.'
        'default'     : False,
    }
)
def greet(parameters):

    output = f'Hello, {parameters.username}!'

    if paramters.uppercase:
        output = output.upper()

    print(output)

MyCLI.invoke(['greet'])
# |Hello, Ralph!

MyCLI.invoke(['greet', 'Phuc'])
# |Hello, Phuc!

MyCLI.invoke(['greet', '--uppercase'])
# |HELLO, RALPH!
```

Multiple UI instances can actually be nested.

```python
MyCLI    = pxd.ui.UI('MyCLI', 'My command line interface.')
MySubCLI = pxd.ui.UI('MySubCLI', 'My smaller command line interface.')

...

MyCLI(MySubCLI)

...

MyCLI.invoke(['MySubCLI', ...])
```

The most important aspect of the UI module is its handling of errors.
In fact,
each UI instance comes with its own `help` verb to print
out the list of verbs alongside their parameters.

<p align="center"><kbd><img src="https://github.com/user-attachments/assets/efba2a48-1ead-4d36-87ec-c3a8632e248e" width="600px"></kbd></p>




# Cite.

The cite module defines a UI instance (although in the future this might be changed
so that it can be run like a regular script).
This UI instance defines some verbs to allow for searching through a codebase for citations
and sources.

The general syntax for a citaiton is as so:
```
@/fieldname fieldvalue/fieldname fieldvalue/`sourcename`
```

An example of a citation to the source `DatasheetXYZ` on page 123, section 4.5:
```
@/pg 123/sec 4.5/`DatasheetXYZ`
```

All sources between the backticks must be defined using the following syntax:
```
@/`sourcename`:
```

Typically some text is placed after the colon to describe the source
(e.g. the full name, the revision number, etc.)

Some citations have sources that are "inlined",
that is, they don't need a source definition.
As of writing,
there's two kinds of inlined citations.
```
@/url:`www.google.com`.
@/by:`Phuc Doan`.
```

The reason why this module exists is because it makes managing citations within a codebase much easier.
Good code will have citations to the appropriate datasheet, reference manual, etc. wherever applicable.
```
configurations.flash_latency            = '0x7'  # @/pg 211/tbl 29/`H7S3rm`.
configurations.flash_programming_delay  = '0b11' # "
configurations.internal_voltage_scaling = {      # @/pg 327/sec 6.8.6/`H7S3rm`.
    'low'  : 0,
    'high' : 1,
}['high']
```

The `cite` UI can search for every instance of citation and do some basic checks on them,
mainly to catch any typos.





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
