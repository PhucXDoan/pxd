import pathlib, types, contextlib, re, traceback, sys, copy, string
from ..pxd.log   import log, ANSI, Indent
from ..pxd.utils import justify, deindent, c_repr, find_dupe, coalesce, OrderedSet



################################################################################################################################
#
# A wrapper around exceptions that
# are thrown during meta-preprocessing.
# The wrapper also provides a routine
# to print out a nice diagnostic.
#

class MetaError(Exception):



    def __init__(self, contexts, underlying_exception):
        self.contexts             = contexts
        self.underlying_exception = underlying_exception



    def dump(self):



        # Load the file and get the lines around the context.

        for context in self.contexts:
            context.lines = [
                ((line_i + 1) - context.line_number, line)
                for line_i, line in enumerate(
                    context.file_path.read_text().splitlines()
                )
                if abs((line_i + 1) - context.line_number) <= 4
            ]



        # Log each context.

        log()

        line_number_just = max([
            len(str(context.line_number + line_delta))
            for context in self.contexts
            for line_delta, line in context.lines
        ] + [0])

        for context_i, context in enumerate(self.contexts):



            # Space between contexts.

            if context_i:
                with Indent(' ' * line_number_just + ' .'):
                    log()
                    log(ANSI('.' * 150, 'fg_bright_black'))
                    log()



            # Show the context.

            log(' ' * line_number_just + ' |')

            for line_delta, line in context.lines:

                with ANSI('bold' if line_delta == 0 else None):



                    # Show the line.

                    line_number = context.line_number + line_delta

                    log(
                        '{} | {}',
                        str(line_number).rjust(line_number_just),
                        ANSI(line, 'bg_red' if line_delta == 0 else None),
                        end = ''
                    )



                    # Show additional information on the line of interest.

                    if line_delta == 0:

                        with ANSI('fg_yellow'):

                            log(f' <- {context.file_path} : {line_number}', end = '')

                            if context.function_name is not None:
                                log(f' : {context.function_name}', end = '')



                    log()

            log(' ' * line_number_just + ' |')

        log()



        # Log the underlying exception.

        with ANSI('fg_red'):

            match self.underlying_exception:



                case SyntaxError():

                    # Sometimes the syntax error message
                    # will also mention a line number, but
                    # it won't be correct. This is a minor
                    # issue, though, so it's probably a no-fix.
                    # e.g:
                    # >
                    # >    "[ERROR] closing parenthesis ')' does not match opening parenthesis '{' on line 10"
                    # >

                    with Indent('[ERROR] ', hanging = True):

                        log(f'Syntax error.')

                        if self.underlying_exception.filename == '<string>':
                            log(
                                f'This seems like a nested SyntaxError exception; '
                                f'the error in the evaluated string might be on line {self.underlying_exception.lineno}.'
                            )

                        log(f'> {self.underlying_exception.args[0]}')



                case NameError() | AttributeError() | ValueError():
                    log(f'[ERROR] {self.underlying_exception}')



                case AssertionError():
                    if self.underlying_exception.args:
                        log(f'[ERROR] {self.underlying_exception.args[0]}')
                    else:
                        log(f'[ERROR] Assertion failed.')



                case KeyError():
                    log(f'[ERROR] Got {type(self.underlying_exception).__name__}.')
                    log(f'        > {self.underlying_exception}')



                case _:
                    log(f'[ERROR] Got {type(self.underlying_exception).__name__}.')
                    if str(self.underlying_exception).strip():
                        log(f'        > {self.underlying_exception}')



################################################################################################################################
#
# The main toolbox used in meta-directives to
# generate nice looking C code in a low-friction way.
#

class __META__:



    def _start(self, meta_directive):
        self.meta_directive = meta_directive
        self.output         = ''
        self.indent         = 0
        self.within_macro   = False
        self.overloads      = {}



    ################################################################################################################################
    #
    # Protect against accidentally using
    # stuff related to code generation
    # when the meta-directive has no file
    # to output it to.
    #

    def __codegen(function):

        def wrapper(self, *args, **kwargs):

            if self.meta_directive.include_directive_file_path is None:
                raise RuntimeError(
                    f'Using `Meta` to generate code is only allowed '
                    f'when the meta-directives has an include-directive.'
                )

            return function(self, *args, **kwargs)

        return wrapper



    ################################################################################################################################
    #
    # Routine that gets invoked at the end of every meta-directive.
    #

    def _end(self):



        # No generated code if there's no #include directive.

        if self.meta_directive.include_directive_file_path is None:
            return



        # We need to insert some stuff at the beginning of the file...

        generated   = self.output
        self.output = ''



        # Indicate origin of the meta-directive in the generated output.

        # TODO Have as an option?
        # self.line(f'''
        #     // [{self.meta_directive.source_file_path.as_posix()}:{self.meta_directive.include_directive_line_number}].
        # ''')



        # Create the master macro for any overloaded macros.
        # This has to be done first because the overloaded macros
        # could be used later in the generated file after they're defined,
        # and if we don't have the master macro to have the overloaded
        # macros be invoked, errors will happen! We could also make the
        # master macro when we're making the first overloaded macro instance,
        # but this master macro could be inside of a #if, making it
        # potentially unexpectedly undefined in certain situations.

        if self.overloads:

            for macro, (parameters, overloading) in self.overloads.items():



                # The overloaded macro instance only has an argument-list if needed.
                #
                # e.g:
                # >                                                              #define SAY(NAME) __MACRO_OVERLOAD__SAY__##NAME
                # >    Meta.define('SAY', ('NAME'), 'meow', NAME = 'CAT')        #define __MACRO_OVERLOAD__SAY__CAT meow
                # >    Meta.define('SAY', ('NAME'), 'bark', NAME = 'DOG')   ->   #define __MACRO_OVERLOAD__SAY__DOG bark
                # >    Meta.define('SAY', ('NAME'), 'bzzz', NAME = 'BUG')        #define __MACRO_OVERLOAD__SAY__BUG bzzz
                # >
                #
                # e.g:
                # >                                                                            #define SAY(NAME, FUNC) __MACRO_OVERLOAD__SAY__##NAME(FUNC)
                # >    Meta.define('SAY', ('NAME', 'FUNC'), 'FUNC(MEOW)', NAME = 'CAT')        #define __MACRO_OVERLOAD__SAY__CAT(FUNC) FUNC(MEOW)
                # >    Meta.define('SAY', ('NAME', 'FUNC'), 'FUNC(BARK)', NAME = 'DOG')   ->   #define __MACRO_OVERLOAD__SAY__DOG(FUNC) FUNC(BARK)
                # >    Meta.define('SAY', ('NAME', 'FUNC'), '     BZZZ ', NAME = 'BUG')        #define __MACRO_OVERLOAD__SAY__BUG(FUNC) BZZZ
                # >
                #

                argument_list = OrderedSet(parameters) - overloading

                if argument_list : argument_list = f'({', '.join(argument_list)})'
                else             : argument_list = ''



                # Output the master macro.

                self.define(
                    f'{macro}({', '.join(parameters)})',
                    f'__MACRO_OVERLOAD__{macro}__##{'##'.join(overloading)}{argument_list}'
                )



        # Put back the rest of the code that was generated.

        if generated:
            self.line(generated)



        # Spit out the generated code.

        pathlib.Path(self.meta_directive.include_directive_file_path).parent.mkdir(parents = True, exist_ok = True)
        pathlib.Path(self.meta_directive.include_directive_file_path).write_text(self.output)



    ################################################################################################################################
    #
    # Helper routine to output lines.
    #
    # Example:
    # >
    # >    Meta.line('''
    # >        printf("%d", 0);
    # >        printf("%d", 1);
    # >        printf("%d", 2);
    # >        printf("%d", 3);
    # >   ''')
    # >
    # >    Meta.line(
    # >        'printf("%d", 0);',
    # >        'printf("%d", 1);',
    # >        'printf("%d", 2);',
    # >        'printf("%d", 3);',
    # >    )
    # >
    # >    Meta.line(f'printf("%d", {i});' for i in range(4))
    # >
    #

    @__codegen
    def line(self, *args):

        if not args: # Create single empty line for `Meta.line()`.
            args = ['''

            ''']

        for arg in args:

            match arg:
                case str() : strings = [arg]
                case _     : strings = list(arg)

            for string in strings:

                for line in deindent(string).splitlines():



                    # Reindent.

                    line = ' ' * 4 * self.indent + line



                    # Escape newlines for multi-lined macros.

                    if self.within_macro:
                        line += '\\'



                    # No trailing spaces.

                    line = line.rstrip()



                    # Next line!

                    self.output += line + '\n'



    ################################################################################################################################
    #
    # Helper routine to handle scopes.
    #
    # Example:
    # >
    # >    with Meta.enter('#if CONDITION'):
    # >        ...
    # >
    # >    with Meta.enter('if (CONDITION)'):
    # >        ...
    # >
    # >    with Meta.enter('#define MACRO'):
    # >        ...
    # >
    #
    # Output:
    # >
    # >    #if CONDITION
    # >        ...
    # >    #endif
    # >
    # >    if (CONDITION)
    # >    {
    # >        ...
    # >    }
    # >
    # >    #define MACRO \
    # >        ... \
    # >        ... \
    # >        ... \
    # >
    #

    @__codegen
    @contextlib.contextmanager
    def enter(self, header = None, opening = None, closing = None, *, indented = None):



        # Determine the scope parameters.

        header_is = lambda *keywords: header is not None and re.search(fr'^\s*({'|'.join(keywords)})\b', header)

        if defining_macro := header_is('#define'):
            self.within_macro = True

        if   defining_macro                                         : suggestion = (None, None      , None)
        elif header_is('#if', '#ifdef', '#elif', '#else')           : suggestion = (None, '#endif'  , None)
        elif header_is('assert', 'static_assert', '_Static_assert') : suggestion = ('(' , ');'      , None)
        elif header_is('struct', 'union', 'enum')                   : suggestion = ('{' , '};'      , None)
        elif header_is('case')                                      : suggestion = ('{' , '} break;', None)
        elif header is not None and header.strip().endswith('=')    : suggestion = ('{' , '};'      , True)
        else                                                        : suggestion = ('{' , '}'       , None)

        if opening  is None: opening  = suggestion[0]
        if closing  is None: closing  = suggestion[1]
        if indented is None: indented = suggestion[2]



        # Header and opening lines.

        if header is not None:
            self.line(header)

        if indented:
            self.indent += 1

        if opening:
            self.line(opening)



        # Body.

        self.indent += 1
        yield
        self.indent -= 1



        # Closing lines.

        if closing is not None:
            self.line(closing)

        if indented:
            self.indent -= 1

        if defining_macro:
            self.within_macro = False
            self.line()



    ################################################################################################################################
    #
    # Helper routine to make enumerations.
    #
    # Example:
    # >
    # >    Meta.enums('Card', 'u32', ('jack', 'queen', 'king', 'ace'))
    # >
    #
    # Example:
    # >
    # >    with Meta.enums('Card', 'u32') as members:
    # >        for card in ('jack', 'queen', 'king', 'ace'):
    # >            members += [card]
    # >
    #
    # Output:
    # >
    # >    enum Card : u32
    # >    {
    # >        Card_jack,
    # >        Card_queen,
    # >        Card_king,
    # >        Card_ace,
    # >    };
    # >    static constexpr u32 Card_COUNT = 4;
    # >
    #



    # The actual routine to create the enumeration is a class so
    # that `Meta.enums` can be used as a context-manager if needed.

    @__codegen
    def enums(self, *args, **kwargs):
        return self.__enums(self, *args, **kwargs)

    class __enums:



        # Whether or not we determine if `Meta.enums` is being used
        # as a context-manager is if the list of members is provided.

        def __init__(
            self,
            meta,
            enum_name,
            enum_type,
            members = None,
            count   = 'constexpr'
        ):

            self.meta      = meta
            self.enum_name = enum_name
            self.enum_type = enum_type
            self.members   = members
            self.count     = count

            if self.members is not None:
                self.__exit__()



        # By using a context-manager, the user can
        # create the list of enumeration members
        # with more complicated logic.

        def __enter__(self):

            if self.members is not None:
                raise ValueError(
                    f'Cannot use `Meta.enums` as a context-manager '
                    f'when members are already provided.'
                )

            self.members = []

            return self.members



        # Here we generate the output whether or
        # not a context-manager was actually used.

        def __exit__(self, *dont_care_about_exceptions):



            # By providing "enum_type", we can specify the width of the enumeration members;
            # this, however, is only supported in C++ and C23.
            # e.g: Meta.enums('Planet', 'u32', ...)   ->   enum Planet : u32 { ... }
            # e.g: Meta.enums('Planet', None , ...)   ->   enum Planet       { ... }

            if self.enum_type is None:
                enum_type_suffix = ''
            else:
                enum_type_suffix = f' : {self.enum_type}'



            # Format the list of members, some of which may be a name-value pair.
            # e.g:
            # >                                       enums Card : u32
            # >    Meta.enums('Card', 'u32', (        {
            # >        ('jack' , 1),                      Card_jack  = 1,
            # >        ('queen', 2),                      Card_queen = 2,
            # >        ('king'    ),             ->       Card_king,
            # >        ('ace'     ),                      Card_ace,
            # >        ('null' , 0),                      Card_null  = 0,
            # >    ))                                 };
            # >

            self.members = list(self.members)

            for member_i, member in enumerate(self.members):

                match member:
                    case (name, value) : value = c_repr(value)
                    case  name         : value = ...

                self.members[member_i] = (f'{self.enum_name}_{c_repr(name)}', value)



            # Output the enumeration members with alignment.

            if self.members:

                with self.meta.enter(f'''
                    enum {self.enum_name}{enum_type_suffix}
                '''):

                    for name, value, just_name in justify(
                        (
                            (None, name ),
                            (None, value),
                            ('<' , name ),
                        )
                        for name, value in self.members
                    ):
                        if value is ...:
                            self.meta.line(f'{name},')
                        else:
                            self.meta.line(f'{just_name} = {value},')



            # When there's no members, we have to forward-declare it,
            # because C doesn't allow empty enumerations.

            else:
                self.meta.line(f'enum {self.enum_name}{enum_type_suffix};')



            # Provide the amount of enumeration members that were defined;
            # this is useful for creating arrays and iterating with
            # for-loops and such.

            match self.count:



                # Don't emit the count.

                case None:
                    pass



                # Use a macro, but this will have the disadvantage of
                # not being scoped and might result in a name conflict.
                # Most of the time, enumerations are defined at the global
                # level, so this wouldn't matter, but enumerations can
                # also be declared within a function; if so, then another
                # enumeration of the same name cannot be declared later
                # or else there'll be multiple #defines with different values.

                case 'define':
                    self.meta.define(f'{self.enum_name}_COUNT', len(self.members))



                # Use a separate, anonymous enumeration definition to make the count.
                # Unlike "define", this will be scoped, so it won't suffer the same
                # issue of name conflicts. However, the compiler could emit warnings
                # if comparisons are made between the enumeration members and this
                # member count, because they are from different enumeration groups.

                case 'enum':
                    self.meta.line(f'''
                        enum{enum_type_suffix} {{ {self.enum_name}_COUNT = {len(self.members)} }};
                    ''')



                # Use a constexpr declaration to declare the member count.
                # Unlike "enum", the type of the constant is the same type
                # as the underlying type of the enumeration, so the compiler
                # shouldn't warn about comparisons between the two.
                # This approach, however, relies on C23 or C++.

                case 'constexpr':
                    self.meta.line(f'''
                        static constexpr {self.enum_type} {self.enum_name}_COUNT = {len(self.members)};
                    ''')



                # Unknown member-count style.

                case unknown:
                    raise ValueError(f'Unknown member-count style of {repr(unknown)}.')



    ################################################################################################################################
    #
    # Helper routine to create C macro definitions.
    #
    # Example:
    # >
    # >    Meta.define('PI', 3.1415)
    # >
    # >    Meta.define('MAX', ('X', 'Y'), '((X) < (Y) ? (Y) : (X))')
    # >
    # >    Meta.define('WORDIFY', ('NUMBER'), 'ZERO' , NUMBER = 0)
    # >    Meta.define('WORDIFY', ('NUMBER'), 'ONE'  , NUMBER = 1)
    # >    Meta.define('WORDIFY', ('NUMBER'), 'TWO'  , NUMBER = 2)
    # >    Meta.define('WORDIFY', ('NUMBER'), 'THREE', NUMBER = 3)
    # >
    #
    # Output:
    # >
    # >    #define PI 3.1415
    # >
    # >    #define MAX(X, Y) ((X) < (Y) ? (Y) : (X))
    # >
    # >    #define WORDIFY(NUMBER) __MACRO_OVERLOAD__WORDIFY__##NUMBER
    # >    #define __MACRO_OVERLOAD__WORDIFY__0 ZERO
    # >    #define __MACRO_OVERLOAD__WORDIFY__1 ONE
    # >    #define __MACRO_OVERLOAD__WORDIFY__2 TWO
    # >    #define __MACRO_OVERLOAD__WORDIFY__3 THREE
    #

    @__codegen
    def define(self, *args, do_while = False, **overloading):



        # Parse syntax of the call.

        match args:



            # e.g: Meta.define('PI', 3.1415)

            case (name, expansion):
                parameters = None



            # e.g: Meta.define('MAX', ('X', 'Y'), '((X) < (Y) ? (Y) : (X))')

            case (name, (*parameters,), expansion):
                pass



            # e.g: Meta.define('TWICE', ('X'), '((X) * 2)')
            # e.g: Meta.define('PI'   , None , 3.1415     )

            case (name, parameter, expansion):
                if parameter is None:
                    parameters = None
                else:
                    parameters = [parameter]



            # Unknown syntax.

            case unknown:
                raise ValueError(
                    f'Not sure what to do with the '
                    f'set of arguments: {repr(args)}.'
                )



        # Macros can be "overloaded" by doing
        # concatenation of a preprocessor-time value.
        # e.g:
        # >
        # >    #define FOOBAR_ABC     3.14
        # >    #define FOOBAR_IJK     1000
        # >    #define FOOBAR_XYZ     "Hello"
        # >    #define FOOBAR(SUFFIX) FOOBAR_##SUFFIX
        # >
        # >    FOOBAR(IJK)   ->   FOOBAR_IJK   ->   1000
        # >

        if overloading:



            # To C values.

            overloading = { key : c_repr(value) for key, value in overloading.items() }



            # Some coherency checks.

            if differences := OrderedSet(overloading) - parameters:
                raise ValueError(
                    f'Overloaded argument "{differences[0]}" not in macro\'s parameter-list.'
                )

            if name in self.overloads and self.overloads[name] != (parameters, tuple(overloading.keys())):
                raise ValueError(
                    f'This overloaded macro instance has a different parameter-list from others.'
                )



            # Make note of the fact that there'll be multiple instances of the "same macro".

            if name not in self.overloads:
                self.overloads[name] = (parameters, tuple(overloading.keys()))



            # The name and parameters of this single macro instance itself.

            name       = f'__MACRO_OVERLOAD__{name}__{'__'.join(map(str, overloading.values()))}'
            parameters = list(OrderedSet(parameters) - overloading) or None



        # Determine the prototype of the macro.

        if parameters is None:
            prototype = f'{name}'
        else:
            prototype = f'{name}({', '.join(parameters)})'



        # Format the macro's expansion.

        expansion = deindent(c_repr(expansion))



        # Output macro that will multiple lines.

        if '\n' in expansion:

            with self.enter(f'#define {prototype}'):



                # Generate multi-lined macro wrapped in do-while.
                # e.g:
                # >
                # >    #define <prototype> \
                # >        do \
                # >        { \
                # >            <expansion> \
                # >            <expansion> \
                # >            <expansion> \
                # >        } \
                # >        while (false) \
                # >

                if do_while:
                    with self.enter('do', '{', '}\nwhile (false)'):
                        self.line(expansion)



                # Generate unwrapped multi-lined macro.
                # e.g:
                # >
                # >    #define <prototype> \
                # >        <expansion> \
                # >        <expansion> \
                # >        <expansion> \
                # >

                else:
                    self.line(expansion)



        # Just output a single-line macro wrapped in do-while.

        elif do_while:
            self.line(f'#define {prototype} do {{ {expansion} }} while (false)')



        # Just output an unwrapped single-line macro.

        else:
            self.line(f'#define {prototype} {expansion}')



    ################################################################################################################################
    #
    # Helper routine to create look-up tables.
    # > e.g:
    # >
    # >    Meta.lut('PLANETS', (
    # >        (
    # >            planet_i,
    # >            ('char*', 'name'  , name  ),
    # >            ('i32'  , 'mass'  , mass  ),
    # >            ('f64'  , 'radius', radius),
    # >        ) for planet_i, (name, mass, radius) in enumerate(PLANETS)
    # >    ))
    # >
    #

    @__codegen
    def lut(self, *arguments):



        # Parse the argument format.

        match arguments:



            # The type for the table is provided.
            # e.g:
            # >
            # >    static const struct <table_type> <table_name>[] =
            # >        {
            # >            [<index>] = { <value>, <value>, <value> },
            # >            [<index>] = { <value>, <value>, <value> },
            # >            [<index>] = { <value>, <value>, <value> },
            # >        };
            # >

            case (table_type, table_name, table_rows):
                pass



            # The type for the table will be created automatically.
            # e.g:
            # >
            # >    static const struct { <type> <name>; <type> <name>; <type> <name>; } <table_name>[] =
            # >        {
            # >            [<index>] = { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >            [<index>] = { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >            [<index>] = { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >        };
            # >

            case (table_name, table_rows):

                table_type = None



            case unknown:
                raise ValueError(f'Unknown set of arguments: {repr(unknown)}.')



        # Make each table row have an index, or have it be `None` if not provided.
        # e.g:
        # >
        # >    Meta.lut(<table_name>, ((
        # >        <index>,
        # >        (<type>, <name>, <value>),
        # >        (<type>, <name>, <value>),
        # >        (<type>, <name>, <value>),
        # >    ) for x in xs))
        # >

        table_rows = list(list(row) for row in table_rows)

        for row_i, row in enumerate(table_rows):
            if row and (isinstance(row[0], tuple) or isinstance(row[0], list)):
                table_rows[row_i] = [None, *row]



        # Determine the type of each member.

        for table_row_i, (row_indexing, *members) in enumerate(table_rows):

            for member_i, member in enumerate(members):

                match member:



                    # The type of each member is explicitly given.
                    # e.g:
                    # >
                    # >    Meta.lut(<table_name>, ((
                    # >        <index>,
                    # >        (<type>, <name>, <value>),
                    # >        (<type>, <name>, <value>),
                    # >        (<type>, <name>, <value>),
                    # >    ) for x in xs))
                    # >

                    case [member_type, member_name, member_value]:

                        if table_type is not None:
                            raise ValueError(
                                f'Member type shouldn\'t be given when '
                                f'the table type is already provided.'
                            )



                    # The type of each member is not given either because
                    # it's not needed or it'll be inferred automatically.
                    # e.g:
                    # >
                    # >    Meta.lut(<table_name>, ((
                    # >        <index>,
                    # >        (<name>, <value>),
                    # >        (<name>, <value>),
                    # >        (<name>, <value>),
                    # >    ) for x in xs))
                    # >

                    case [member_name, member_value]:

                        member_type = None



                    case unknown:
                        raise ValueError(f'Unknown row member format: {repr(unknown)}.')



                members[member_i] = [member_type, member_name, c_repr(member_value)]



            table_rows[table_row_i] = [row_indexing, members]



        # Determine the table type.

        if table_type is None:

            match table_rows:



                # This is just how we're going to handle empty tables.

                case []:

                    table_type = 'struct {}'



                # Create the type for the table.

                case [[first_row_indexing, first_row_members], *rest]:

                    table_type = f'struct {{ {' '.join(
                        [
                            f'{member_type if member_type is not None else f'typeof({member_value})'} {member_name};'
                            for member_type, member_name, member_value in first_row_members
                        ] if table_rows else []
                    )} }}'



                case unknown:
                    assert False, unknown



        # Generate the table with nice, aligned columns.

        with self.enter(f'static const {table_type} {table_name}[] ='):

            for just_row_indexing, *just_fields in justify(
                (
                    ('<', f'[{row_indexing}] = ' if row_indexing is not None else ''),
                    *(
                        ('<', f'.{member_name} = {member_value}')
                        for member_type, member_name, member_value in members
                    ),
                )
                for row_indexing, members in table_rows
            ):
                self.line(f'{just_row_indexing}{{ {', '.join(just_fields)} }},')



################################################################################################################################
#
# The main routine to run the meta-preprocessor.
#

def do(*,
    output_directory_path,
    source_file_paths,
    callback = None,
):

    output_directory_path = pathlib.Path(output_directory_path)
    source_file_paths     = tuple(map(pathlib.Path, source_file_paths))



    ################################################################################################################################
    #
    # Routine to parse the C preprocessor's include-directive.
    #

    def get_include_directive_file_path(line):



        # It's fine if the line is commented;
        # this would mean that the meta-directive
        # would still generate code, but where the
        # meta-directive is isn't where the code
        # would be inserted at right now.
        # e.g:
        # >
        # >    // #include "output.meta"
        # >    /* #meta
        # >        ...
        # >    */
        # >

        line = line.strip()

        if   line.startswith('//'): line = line.removeprefix('//')
        elif line.startswith('/*'): line = line.removeprefix('/*')



        # Check if the line has an include directive.

        line = line.strip()

        if not line.startswith(prefix := '#'):
            return None

        line = line.removeprefix(prefix)

        line = line.strip()

        if not line.startswith(prefix := 'include'):
            return None

        line = line.removeprefix(prefix)



        # Look for the file path.

        line = line.strip()

        end_quote = {
            '<' : '>',
            '"' : '"',
        }.get(line[0], None) if line else None

        if end_quote is None:
            return None

        length = line[1:].find(end_quote)

        if length == -1:
            return None

        return pathlib.Path(output_directory_path, line[1:][:length])



    ################################################################################################################################
    #
    # Get all of the meta-directives.
    #

    meta_directives = []

    for source_file_path in source_file_paths:

        remaining_lines       = source_file_path.read_text().splitlines()
        remaining_line_number = 1

        while True:



            # Check if the current line is an include-directive.

            if not remaining_lines:
                break

            include_directive_file_path = get_include_directive_file_path(remaining_lines[0])

            if include_directive_file_path is None:

                include_directive_line_number = None

            else:

                include_directive_line_number  = remaining_line_number
                remaining_lines                = remaining_lines[1:]
                remaining_line_number         += 1



            # We'll be now checking if the current line is a meta-header.

            if not remaining_lines:
                break

            meta_header_line         = remaining_lines[0]
            meta_header_line_number  = remaining_line_number
            remaining_lines          = remaining_lines[1:]
            remaining_line_number   += 1



            # Only in Python files that meta-headers are not prefixed with `/*`.

            if source_file_path.suffix != '.py':

                meta_header_line = meta_header_line.strip()

                if not meta_header_line.startswith(prefix := '/*'):
                    continue

                meta_header_line = meta_header_line.removeprefix(prefix)



            # Check for the meta-header tag.

            meta_header_line = meta_header_line.strip()

            if not meta_header_line.startswith(prefix := '#meta'):

                if not meta_header_line.startswith('#') and source_file_path.suffix == '.py':

                    # Python files that are meta-directives
                    # should have the meta-header at the top.
                    break

                else:

                    continue

            meta_header_line = meta_header_line.removeprefix(prefix)



            # We then parse and validate the meta-header.

            match meta_header_line.split(':'):

                case [exports]:
                    ports            = [exports, '']
                    has_import_field = False

                case [exports, imports]:
                    ports            = [exports, imports]
                    has_import_field = True

                case _: assert False



            # Process the LHS and RHS.

            for port_i, port in enumerate(ports):

                symbols = []

                for symbol in port.split(','):

                    symbol = symbol.strip()

                    if symbol == '':
                        continue # We're fine with extra commas.

                    if not symbol.isidentifier():
                        raise MetaError(
                            [
                                types.SimpleNamespace(
                                    file_path     = source_file_path,
                                    line_number   = meta_header_line_number,
                                    function_name = None,
                                ),
                            ],
                            SyntaxError(
                                f'The symbol {repr(symbol)} doesn\'t '
                                f'look like an identifier.'
                            )
                        )

                    symbols += [symbol]



                # We're find with duplicate symbols;
                # doesn't really affect anything besides being redundant.

                ports[port_i] = OrderedSet(symbols)



            exports, imports = ports



            # Get the lines of the meta-directive.

            body_lines = []

            match source_file_path.suffix:


                # Python files are interpreted as the entire meta-directive.

                case '.py':

                    body_lines             = remaining_lines
                    remaining_line_number += len(remaining_lines)
                    remaining_lines        = []



                # The end of the meta-directive is denoted by `*/`.

                case _:

                    ending = -1

                    while ending == -1:



                        # Get next line of the body.

                        if not remaining_lines:
                            raise MetaError(
                                [
                                    types.SimpleNamespace(
                                        file_path     = source_file_path,
                                        line_number   = meta_header_line_number,
                                        function_name = None,
                                    )
                                ],
                                SyntaxError(
                                    f"Couldn't find the terminating '*/'."
                                )
                            )

                        body_line              = remaining_lines[0]
                        remaining_lines        = remaining_lines[1:]
                        remaining_line_number += 1



                        # Check if we have found the ending.

                        ending = body_line.find('*/')

                        if ending != -1:
                            body_line = body_line[:ending]



                        # Append.

                        body_line   = body_line.rstrip()
                        body_lines += [body_line]



            # Finished processing this meta-directive.

            meta_directives += [types.SimpleNamespace(
                source_file_path              = source_file_path,
                meta_header_line_number       = meta_header_line_number,
                include_directive_file_path   = include_directive_file_path,
                include_directive_line_number = include_directive_line_number,
                exports                       = exports,
                imports                       = imports,
                explicit_imports              = imports,
                global_exporter               = has_import_field and not imports,
                body_lines                    = body_lines,
                bytecode_name                 = None,
            )]



    ################################################################################################################################
    #
    # Check consistency of exports and imports.
    #



    for include_directive_file_path, meta_directives_of_include_directive_file_path in coalesce(
        (meta_directive.include_directive_file_path, meta_directive)
        for meta_directive in meta_directives
        if meta_directive.include_directive_file_path is not None
    ):
        if len(meta_directives_of_include_directive_file_path) >= 2:
            raise MetaError(
                [
                    types.SimpleNamespace(
                        file_path     = meta_directive.source_file_path,
                        line_number   = meta_directive.include_directive_line_number,
                        function_name = None,
                    )
                    for meta_directive in meta_directives_of_include_directive_file_path
                ],
                RuntimeError(
                    f'Meta-directives with the same output '
                    f'file path: "{include_directive_file_path}".'
                )
            )



    for symbol, meta_directives_of_symbol in coalesce(
        (symbol, meta_directive)
        for meta_directive in meta_directives
        for symbol in meta_directive.exports
    ):
        if len(meta_directives_of_symbol) >= 2:
            raise MetaError(
                [
                    types.SimpleNamespace(
                        file_path     = meta_directive.source_file_path,
                        line_number   = meta_directive.meta_header_line_number,
                        function_name = None,
                    )
                    for meta_directive in meta_directives_of_symbol
                ],
                RuntimeError(f'Multiple meta-directives export the symbol "{symbol}".')
            )



    all_exports = OrderedSet(
        export
        for meta_directive in meta_directives
        for export         in meta_directive.exports
    )

    for meta_directive in meta_directives:

        for symbol in meta_directive.imports:

            if symbol in meta_directive.exports:
                raise MetaError(
                    [
                        types.SimpleNamespace(
                            file_path     = meta_directive.source_file_path,
                            line_number   = meta_directive.meta_header_line_number,
                            function_name = None,
                        ),
                    ],
                    RuntimeError(f'Meta-directives exports "{symbol}" but also imports it.')
                )

            if symbol not in all_exports:
                raise MetaError(
                    [
                        types.SimpleNamespace(
                            file_path     = meta_directive.source_file_path,
                            line_number   = meta_directive.meta_header_line_number,
                            function_name = None,
                        ),
                    ],
                    RuntimeError(
                        f'Meta-directives imports "{symbol}" '
                        f'but no meta-directive exports that.'
                    )
                )



    ################################################################################################################################
    #
    # Perform implicit importings.
    # >
    # >    #meta                     -> No exports; import everything.
    # >    #meta A, B, C             -> Export A, B, and C; no explicit imports.
    # >    #meta A, B, C :           -> Export A, B, and C and have every other meta-directive implicitly globally import A, B, C.
    # >    #meta A, B, C : D, E, F   -> Export A, B, and C; explicitly import D, E, and F.
    # >    #meta         : D, E, F   -> Export nothing; explicitly import D, E, and F.
    # >    #meta         :           -> No exports; no imports at all.
    # >
    #



    # If it's just a bare meta-header,
    # then the meta-directive implicitly
    # imports everything.

    for meta_directive in meta_directives:
        if not (
            meta_directive.exports
            or meta_directive.imports
            or meta_directive.global_exporter
        ):
            meta_directive.imports = all_exports



    # If the meta-directive explicitly imports
    # nothing, then its exports will globally be
    # implicitly imported into every other meta-directive.

    implicit_global_import = OrderedSet(
        symbol
        for meta_directive in meta_directives
        if meta_directive.global_exporter
        for symbol in meta_directive.exports
    )

    for meta_directive in meta_directives:
        if not meta_directive.global_exporter:
            meta_directive.imports |= implicit_global_import



    ################################################################################################################################
    #
    # Sort the meta-directives.
    #

    remaining_meta_directives = meta_directives
    meta_directives           = []
    available_symbols         = OrderedSet()

    while remaining_meta_directives:

        for meta_directive_i, meta_directive in enumerate(remaining_meta_directives):



            # This meta-directive doesn't have
            # all of its imports satisfied yet.

            if not all(symbol in available_symbols for symbol in meta_directive.imports):
                continue



            # This meta-directive would be executed and define all
            # of its exported symbols for later meta-directives to use.

            available_symbols |= meta_directive.exports



            # Remove from pool.

            meta_directives += [meta_directive]
            del remaining_meta_directives[meta_directive_i]

            break



        # Couldn't find the next meta-directive to execute.

        else:
            raise MetaError(
                [
                    types.SimpleNamespace(
                        file_path     = meta_directive.source_file_path,
                        line_number   = meta_directive.meta_header_line_number,
                        function_name = None,
                    )
                    for meta_directive in remaining_meta_directives
                    if meta_directive.explicit_imports
                ],
                RuntimeError(f'Meta-directives with circular dependency.')
            )



    ################################################################################################################################
    #
    # The meta-decorator that handles the the set-up
    # and resolution of a meta-directive's execution.
    #

    current_meta_directive_index = 0
    Meta                         = __META__()

    def __META_DECORATOR__(meta_globals):

        def decorator(function):

            nonlocal current_meta_directive_index, Meta



            # This should be the meta-directive that we're executing now.

            meta_directive = meta_directives[current_meta_directive_index]



            # Start of the callback.

            if callback is None:
                callback_iterator = None

            else:

                callback_iterator = callback(current_meta_directive_index, meta_directives)

                if not isinstance(callback_iterator, types.GeneratorType):
                    raise RuntimeError('Callback must be a generator.')

                try:
                    next(callback_iterator)
                except StopIteration:
                    raise RuntimeError('The callback did not yield.')



            # Meta is special in that it needs to be a
            # global singleton. This is for meta-directives
            # that define functions that use Meta itself
            # to generate code, and that function might
            # be called in a different meta-directive.
            # They all need to refer to the same object,
            # so one singleton must be made for everyone
            # to refer to. Still, checks are put in place
            # to make Meta illegal to use in meta-directives
            # that do not have an associated include-directive.

            function_globals = { 'Meta' : Meta }



            # We deepcopy exported values to be then put in
            # the function's global namespace so that if a
            # meta-directive mutates it for some reason, it'll
            # only be contained within that meta-directive;
            # this isn't really necessary, but since meta-directives
            # are evaluated mostly out-of-order, it helps keep the
            # uncertainty factor lower. This, however, does induce
            # a performance hit if the object is quite large.

            for symbol in meta_directive.imports:

                # Modules are not deepcopy-able.
                if isinstance(meta_globals[symbol], types.ModuleType):
                    function_globals[symbol] = meta_globals[symbol]
                else:
                    function_globals[symbol] = copy.deepcopy(meta_globals[symbol])



            # Execute the meta-directive.

            Meta._start(meta_directive)
            types.FunctionType(function.__code__, function_globals)()
            Meta._end()



            # Copy the exported symbols into the
            # collective symbol namespace so far.

            for symbol in meta_directive.exports:

                if symbol not in function_globals:
                    raise MetaError(
                        [
                            types.SimpleNamespace(
                                file_path     = meta_directive.source_file_path,
                                line_number   = meta_directive.meta_header_line_number,
                                function_name = None,
                            )
                        ],
                        RuntimeError(f'Symbol "{symbol}" was not defined.')
                    )

                meta_globals[symbol] = function_globals[symbol]



            # End of callback.

            if callback is not None:

                try:
                    callback_iterator.send(Meta.output)
                    stopped = False
                except StopIteration:
                    stopped = True

                if not stopped:
                    raise RuntimeError('The callback did not return.')



            # Onto next meta-directive!

            current_meta_directive_index += 1



        return decorator



    ################################################################################################################################
    #
    # Routine to handle exceptions that occured
    # during compilation or execution of meta-directives.
    #

    def diagnose(error):



        # Get the tracebacks after we begin executing
        # the meta-directive's Python snippet.

        traces = traceback.extract_tb(sys.exc_info()[2])

        while traces and traces[0].name != '__META_DIRECTIVE__':
            del traces[0]

        contexts = []



        # A meta-directive caused this syntax error.

        if isinstance(error, SyntaxError) and not traces:

            meta_directive = [
                meta_directive
                for meta_directive in meta_directives
                if meta_directive.bytecode_name == error.filename
            ]

            if not meta_directive:
                # Syntax error somewhere else obscure
                # e.g: meta-directive running `exec` or importing.
                raise

            meta_directive, = meta_directive

            contexts += [types.SimpleNamespace(
                function_name = None,
                file_path     = meta_directive.source_file_path,
                line_number   = (
                    (meta_directive.meta_header_line_number + 1)
                        + error.lineno
                        - meta_directive.body_line_number
                ),
            )]



        # For most errors we can inspect the traceback
        # to show all the levels of function calls.

        else:



            # Something else might've happened outside of the meta-directive.
            # TODO Example?

            if not traces:
                raise



            # Find each level of the stack; some might be in a
            # meta-directive while others are in a imported module.

            for trace in traces:

                meta_directive = [
                   meta_directive
                   for meta_directive in meta_directives
                   if meta_directive.bytecode_name == trace.filename
                ]

                if meta_directive:
                    meta_directive,     = meta_directive
                    context_file_path   = meta_directive.source_file_path
                    context_line_number = (
                        (meta_directive.meta_header_line_number + 1)
                            + trace.lineno
                            - meta_directive.body_line_number
                    )
                else:
                    context_file_path   = pathlib.Path(trace.filename)
                    context_line_number = trace.lineno

                contexts += [types.SimpleNamespace(
                    file_path     = context_file_path,
                    line_number   = context_line_number,
                    function_name = '#meta' if trace.name == '__META_DIRECTIVE__' else trace.name,
                )]



        # User deals with the exception now.

        raise MetaError(contexts, error) from error



    ################################################################################################################################
    #
    # Compile each meta-directive to catch any syntax errors.
    #

    for meta_directive in meta_directives:



        # Every meta-directive is executed within
        # a function context wrapped by the decorator.

        meta_code = [
            f'@__META_DECORATOR__(__META_GLOBALS__)',
            f'def __META_DIRECTIVE__():',
        ]



        # List the things that the function is
        # expected to define in the global namespace.

        if meta_directive.exports:
            meta_code += [
                f'',
                f'    global {', '.join(meta_directive.exports)}',
            ]



        # If the #meta directive has no code and
        # doesn't export anything, the function
        # would end up empty, which is invalid Python
        # syntax; having a `pass` is a simple fix
        # for this edge case.

        meta_code += ['    pass']



        # Inject the meta-directive's Python snippet.

        meta_code += ['']

        meta_directive.body_line_number = len(meta_code) + 1

        meta_code += [
            (' ' * (4 if line else 0)) + line
            for line in deindent(
                '\n'.join(meta_directive.body_lines),
                multilined_string_literal = False,
                single_line_comment       = '#'
            ).splitlines()
        ]



        # Compile the meta-directive; this has to
        # be done for each meta-directive individually
        # rather than all together at once because a
        # syntax error can "leak" across multiple meta-directives,
        # to which it's then hard to identify where the
        # exact source of the syntax error is.

        meta_directive.bytecode_name = f'MetaDirective({meta_directive.source_file_path}:{meta_directive.meta_header_line_number})'

        try:
            meta_directive.bytecode = compile('\n'.join(meta_code), meta_directive.bytecode_name, 'exec')
        except Exception as error:
            diagnose(error)



    ################################################################################################################################
    #
    # We now finally execute the meta-directives.
    #

    output_directory_path.mkdir(parents = True, exist_ok = True)

    globals = { '__META_DECORATOR__' : __META_DECORATOR__, '__META_GLOBALS__' : {} }

    for meta_directive in meta_directives:
        try:
            exec(meta_directive.bytecode, globals, {})
        except Exception as error:
            diagnose(error)
