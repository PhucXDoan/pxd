import pathlib, types, contextlib, re, traceback, builtins, sys, copy
from ..pxd.log   import log
from ..pxd.utils import ljusts, root, deindent, repr_in_c, mk_dict, find_dupe, coalesce, Obj, Record, OrdSet, ErrorLift

# TODO Warn on unused symbols.

class MetaError(Exception):

    def __init__(
        self,
        diagnostic                = None, *,
        undefined_exported_symbol = None,
        source_file_path          = None,
        meta_header_line_number   = None
    ):
        self.diagnostic                = diagnostic
        self.undefined_exported_symbol = undefined_exported_symbol # When a meta-directive doesn't define a symbol it said it'd export.
        self.source_file_path          = source_file_path          # "
        self.meta_header_line_number   = meta_header_line_number   # "

    def __str__(self):
        return self.diagnostic

################################################################################################################################
#
# The main toolbox used in Meta-directives to generate nice looking C code in a low-friction way.
#

class __META__:



    def __init__(self):
        self.include_directive_file_path = None



    def _start(self, meta_directive):
        self.meta_directive = meta_directive
        self.output         = ''
        self.indent         = 0
        self.within_macro   = False
        self.overloads      = {}



    ################################################################################################################################
    #
    # Protect against accidentally using stuff related to code generation
    # when the meta-directive has no file to output it to.
    #

    def _codegen(function):

        def wrapper(self, *args, **kwargs):

            if self.meta_directive.include_directive_file_path is None:
                raise MetaError('Meta used in a meta-directive that has no associated include file path.')

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

        self.line(f'// [{self.meta_directive.source_file_path}:{self.meta_directive.include_directive_line_number}].')



        # Create the master macro for any overloaded macros.
        # This has to be done first because the overloaded macros could be used later in the generated file after they're defined,
        # and if we don't have the master macro to have the overloaded macros be invoked, errors will happen!
        # We could also make the master macro when we're making the first overloaded macro instance,
        # but this master macro could be inside of a #if, making it potentially unexpectedly undefined in certain situations.

        if self.overloads:

            for macro, (parameters, overloading) in self.overloads.items():



                # The overloaded macro instance only has an argument-list if needed.
                #
                # e.g:
                # >                                                              #define SAY(NAME) MACRO_OVERLOAD__SAY__##NAME
                # >    Meta.define('SAY', ('NAME'), 'meow', NAME = 'CAT')        #define MACRO_OVERLOAD__SAY__CAT meow
                # >    Meta.define('SAY', ('NAME'), 'bark', NAME = 'DOG')   ->   #define MACRO_OVERLOAD__SAY__DOG bark
                # >    Meta.define('SAY', ('NAME'), 'bzzz', NAME = 'BUG')        #define MACRO_OVERLOAD__SAY__BUG bzzz
                # >
                #
                # e.g:
                # >                                                                            #define SAY(NAME, FUNC) MACRO_OVERLOAD__SAY__##NAME(FUNC)
                # >    Meta.define('SAY', ('NAME', 'FUNC'), 'FUNC(MEOW)', NAME = 'CAT')        #define MACRO_OVERLOAD__SAY__CAT(FUNC) FUNC(MEOW)
                # >    Meta.define('SAY', ('NAME', 'FUNC'), 'FUNC(BARK)', NAME = 'DOG')   ->   #define MACRO_OVERLOAD__SAY__DOG(FUNC) FUNC(BARK)
                # >    Meta.define('SAY', ('NAME', 'FUNC'), '     BZZZ ', NAME = 'BUG')        #define MACRO_OVERLOAD__SAY__BUG(FUNC) BZZZ
                # >
                #

                argument_list = OrdSet(parameters) - OrdSet(overloading)

                if argument_list : argument_list = f'({', '.join(argument_list)})'
                else             : argument_list = ''



                # Output the master macro.

                self.define(f'{macro}({', '.join(parameters)})', f'MACRO_OVERLOAD__{macro}__##{'##'.join(overloading)}{argument_list}')



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

    @_codegen
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

    @_codegen
    @contextlib.contextmanager
    def enter(self, header = None, opening = None, closing = None, *, indented = None):



        # Determine the scope parameters.

        header_is = lambda *keywords: header is not None and re.search(fr'^\s*({'|'.join(keywords)})\b', header)

        if defining_macro := header_is('#define'):
            self.within_macro = True

        if   defining_macro                                      : suggestion = (None, None      , None)
        elif header_is('#if', '#ifdef', '#elif', '#else')        : suggestion = (None, '#endif'  , None)
        elif header_is('struct', 'union', 'enum')                : suggestion = ('{' , '};'      , None)
        elif header_is('case')                                   : suggestion = ('{' , '} break;', None)
        elif header is not None and header.strip().endswith('=') : suggestion = ('{' , '};'      , True)
        else                                                     : suggestion = ('{' , '}'       , None)

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

    @_codegen
    def enums(self, *args, **kwargs):
        return self.__enums(self, *args, **kwargs)

    class __enums:



        # Whether or not we determine if `Meta.enums` is being used as a context-manager is if the list of members is provided.

        def __init__(self, meta, enum_name, enum_type, members = None, count = 'constexpr'):

            self.meta      = meta
            self.enum_name = enum_name
            self.enum_type = enum_type
            self.members   = members
            self.count     = count

            if self.members is not None:
                self.__exit__()



        # By using a context-manager, the user can create the list of enumeration members with more complicated logic.

        def __enter__(self):

            if self.members is not None:
                raise ValueError('Cannot use Meta.enums in a with-context when members are already provided: {self.members}.')

            self.members = []

            return self.members



        # Here we generate the output whether or not a context-manager was actually used.

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
                    case (name, value) : value = repr_in_c(value)
                    case  name         : value = ...

                self.members[member_i] = (f'{self.enum_name}_{repr_in_c(name)}', value)



            # Output the enumeration members with alignment.

            with self.meta.enter(f'enum {self.enum_name}{enum_type_suffix}'):

                for member, ljust_name in zip(self.members, ljusts(name for name, value in self.members)):

                    match member:
                        case (name, builtins.Ellipsis) : self.meta.line(f'{name},'                )
                        case (name, value            ) : self.meta.line(f'{ljust_name} = {value},')



            # Provide the amount of enumeration members that were defined;
            # this is useful for creating arrays and iterating with for-loops and such.

            match self.count:



                # Don't emit the count.

                case None:
                    pass



                # Use a macro, but this will have the disadvantage of not being scoped and might result in a name conflict.
                # Most of the time, enumerations are defined at the global level, so this wouldn't matter, but enumerations can
                # also be declared within a function; if so, then another enumeration of the same name cannot be declared later
                # or else there'll be multiple #defines with different values.

                case 'define':
                    self.meta.define(f'{self.enum_name}_COUNT', len(self.members))



                # Use a separate, anonymous enumeration definition to make the count.
                # Unlike "define", this will be scoped, so it won't suffer the same issue of name conflicts.
                # However, the compiler could emit warnings if comparisons are made between the enumeration
                # members and this member count, because they are from different enumeration groups.

                case 'enum':
                    self.meta.line(f'enum{enum_type_suffix} {{ {self.enum_name}_COUNT = {len(self.members)} }};')



                # Use a constexpr declaration to declare the member count.
                # Unlike "enum", the type of the constant is the same type as the underlying type of the enumeration,
                # so the compiler shouldn't warn about comparisons between the two.
                # This approach, however, relies on C23 or C++.

                case 'constexpr':
                    self.meta.line(f'static constexpr {self.enum_type} {self.enum_name}_COUNT = {len(self.members)};')



                # Unknown member-count style.

                case _:
                    assert False



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
    # >    #define WORDIFY(NUMBER) MACRO_OVERLOAD__WORDIFY__##NUMBER
    # >    #define MACRO_OVERLOAD__WORDIFY__0 ZERO
    # >    #define MACRO_OVERLOAD__WORDIFY__1 ONE
    # >    #define MACRO_OVERLOAD__WORDIFY__2 TWO
    # >    #define MACRO_OVERLOAD__WORDIFY__3 THREE
    #

    @_codegen
    def define(self, *args, do_while = False, **overloading):



        # Parse syntax of the call.

        match args:



            # e.g: Meta.define('PI', 3.1415)

            case [name, expansion]:
                parameters = None



            # e.g: Meta.define('MAX', ('X', 'Y'), '((X) < (Y) ? (Y) : (X))')

            case [name, (*parameters,), expansion]:
                pass



            # e.g: Meta.define('TWICE', ('X'), '((X) * 2)')
            # e.g: Meta.define('PI'   , None , 3.1415     )

            case [name, parameter, expansion]:
                if parameter is None:
                    parameters = None
                else:
                    parameters = [parameter]



            # Unknown syntax.

            case _:
                assert False



        # Macros can be "overloaded" by doing concatenation of a preprocessor-time value.
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

            overloading = { key : repr_in_c(value) for key, value in overloading.items() }



            # Some coherency checks.

            if differences := OrdSet(overloading) - OrdSet(parameters):
                raise ValueError(f'Overloading a macro ("{name}") on the parameter "{differences[0]}", but it\'s not in the parameter-list: {parameters}.')

            if name in self.overloads and self.overloads[name] != (parameters, tuple(overloading.keys())):
                raise ValueError(f'Cannot overload a macro ("{name}") with differing overloaded parameters.')



            # Make note of the fact that there'll be multiple instances of the "same macro".

            if name not in self.overloads:
                self.overloads[name] = (parameters, tuple(overloading.keys()))



            # The name and parameters of this single macro instance itself.

            name       = f'MACRO_OVERLOAD__{name}__{'__'.join(map(str, overloading.values()))}'
            parameters = list(OrdSet(parameters) - OrdSet(overloading)) or None



        # Determine the prototype of the macro.

        if parameters is None:
            prototype = f'{name}'
        else:
            prototype = f'{name}({', '.join(parameters)})'



        # Format the macro's expansion.

        expansion = deindent(repr_in_c(expansion))



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
    # Helper routine to create multiple if-statements.
    #
    # Example:
    # >
    # >    @Meta.ifs(['A', 'B', 'C'], '#elif')
    # >    def _(x):
    # >
    # >        ...
    # >
    # >        yield f'check({x})'
    # >
    # >        ...
    # >
    #
    # Output:
    # >
    # >    #if check(A)
    # >        ...
    # >    #elif check(B)
    # >        ...
    # >    #elif check(C)
    # >        ...
    # >    #endif
    # >

    @_codegen
    def ifs(self, items, style):

        items = tuple(items)

        def decorator(func):

            for item_i, item in enumerate(items):



                # First iteration of the function should give us the condition of the if-statement.

                iterator = func(item)

                try:
                    condition = next(iterator)
                except StopIteration:
                    raise RuntimeError(ErrorLift("The function didn't yield for the condition of the if-statement."))



                # Then generate the if-statement according to the desired style.

                match item_i, style:
                    case _, 'if'      : entrance = (f'if ({condition})'     , None, None                               )
                    case 0, 'else if' : entrance = (f'if ({condition})'     , None, None                               )
                    case _, 'else if' : entrance = (f'else if ({condition})', None, None                               )
                    case _, '#if'     : entrance = (f'#if {condition}'      , None, None                               )
                    case 0, '#elif'   : entrance = (f'#if {condition}'      , None, '#endif' if len(items) == 1 else '')
                    case _, '#elif'   : entrance = (f'#elif {condition}'    , None, None                               )
                    case _            : raise ValueError(ErrorLift(f'Unknown if-statement style of "{style}".'))



                # Next iteration of the function should generate the code within the if-statement.

                with self.enter(*entrance):

                    stopped = False

                    try:
                        next(iterator)
                    except StopIteration:
                        stopped = True

                    if not stopped:
                        raise RuntimeError(ErrorLift('The function should only yield once to make the if-statement.'))



        return decorator



    ################################################################################################################################
    #
    # Helper routine to create look-up tables.
    #
    # Example:
    # >
    # >    Meta.lut('PLANETS', ((
    # >        ('char*', 'name'  , planet.name  ),
    # >        ('f32'  , 'mass'  , planet.mass  ),
    # >        ('f32'  , 'radius', planet.radius),
    # >    ) for planet in planets))
    # >
    #
    # Output:
    # >
    # >    static const struct { char* name; f32 mass; f32 radius; } PLANETS[] =
    # >        {
    # >            { .name = <value>, .mass = <value>, .radius = <value> },
    # >            { .name = <value>, .mass = <value>, .radius = <value> },
    # >            { .name = <value>, .mass = <value>, .radius = <value> },
    # >        };
    # >

    @_codegen
    def lut(self, table_name, entries):



        # e.g: Meta.lut(<table_name>, (f(x) for x in xs))

        entries = tuple(entries)



        # If the first element of every entry's field-list is a non-tuple, then we assume that is the index of the entry.
        # e.g:
        # >
        # >    Meta.lut(<table_name>, ((             static const struct { <type> <name>; <type> <name>; <type> <name>; } <table_name>[] =
        # >        <index>,                              {
        # >        (<type>, <name>, <value>),   ->           [<index>] = { .<name> = <value>, .<name> = <value>, .<name> = <value> },
        # >        (<type>, <name>, <value>),                [<index>] = { .<name> = <value>, .<name> = <value>, .<name> = <value> },
        # >        (<type>, <name>, <value>),                [<index>] = { .<name> = <value>, .<name> = <value>, .<name> = <value> },
        # >    ) for x in xs))                           };
        # >

        if all(entry and not isinstance(entry[0], tuple) for entry in entries):
            indices = [repr_in_c(index) for index, *fields in entries]
            entries = [fields           for index, *fields in entries]



        # The entries of the look-up table will be defined in sequential order with no explicit indices.
        # e.g:
        # >
        # >    Meta.lut(<table_name>, ((             static const struct { <type> <name>; <type> <name>; <type> <name>; } <table_name>[] =
        # >        (<type>, <name>, <value>),            {
        # >        (<type>, <name>, <value>),   ->           { .<name> = <value>, .<name> = <value>, .<name> = <value> },
        # >        (<type>, <name>, <value>),                { .<name> = <value>, .<name> = <value>, .<name> = <value> },
        # >    ) for x in xs))                               { .<name> = <value>, .<name> = <value>, .<name> = <value> },
        # >                                             };
        # >

        else:
            indices = None



        # The "table_name" argument can specify the type of the look-up table.

        match table_name:



            # If the type for the look-up table's entries is given, then each field shouldn't have to specify the type.
            # e.g:
            # >
            # >    Meta.lut((<table_type>, <table_name>), ((        static const <table_type> <table_name>[] =
            # >        (name, value),                                   {
            # >        (name, value),                          ->           { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >        (name, value),                                       { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >    ) for x in xs))                                          { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >                                                         };
            # >

            case (table_type, table_name):

                values = [
                    [f'.{name} = {repr_in_c(value)}' for name, value in entry]
                    for entry in entries
                ]

                field_names_per_entry = [
                    (name for name, value in entry)
                    for entry in entries
                ]



            # If the type for the look-up table's entries is not given, then we'll create the type based on the type of each field.
            # e.g:
            # >
            # >    Meta.lut(<table_name>, ((             static const struct { <type> <name>; <type> <name>; <type> <name>; } <table_name>[] =
            # >        (<type>, <name>, <value>),            {
            # >        (<type>, <name>, <value>),   ->           { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >        (<type>, <name>, <value>),                { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >    ) for x in xs))                               { .<name> = <value>, .<name> = <value>, .<name> = <value> },
            # >                                              };
            # >

            case table_name:

                members = OrdSet(
                    f'{type} {name};'
                    for entry in entries
                    for type, name, value in entry
                )

                table_type = f'struct {{ {' '.join(members)} }}'

                values = [
                    [repr_in_c(value) for type, name, value in entry]
                    for entry in entries
                ]

                field_names_per_entry = [
                    [name for type, name, value in entry]
                    for entry in entries
                ]



        # Some coherency checks.

        if indices is not None and (dupe := find_dupe(indices)) is not None:
            raise ValueError(ErrorLift(f'Look-up table has duplicate index of "{dupe}".'))

        for field_names in field_names_per_entry:
            if (dupe := find_dupe(field_names)) is not None:
                raise ValueError(ErrorLift(f'Look-up table has an entry with duplicate field of "{dupe}".'))



        # Output the look-up table.

        lines = ['{ ' + ', '.join(value) + ' },' for value in ljusts(values)]

        if indices is not None:
            lines = [f'[{index}] = {value}' for index, value in zip(ljusts(indices), lines)]

        with self.enter(f'static const {table_type} {table_name}[] ='):
            self.line(lines)



################################################################################################################################
#
# The main routine to run the meta-preprocessor.
#

def do(*,
    output_directory_path,
    source_file_paths,
    meta_py_file_path = None,
    callback          = None,
):



    # By default, we'll make a `__meta__.py` file that has all
    # of the meta-directive's code put together to be then executed.

    if meta_py_file_path is None:
        meta_py_file_path = pathlib.Path(output_directory_path, '__meta__.py')



    # Convert to pathlib.Path.

    output_directory_path = pathlib.Path(output_directory_path)
    source_file_paths     = tuple(map(pathlib.Path, source_file_paths))
    meta_py_file_path     = pathlib.Path(meta_py_file_path)



    ################################################################################################################################
    #
    # Routine to parse the C preprocessor's include-directive.
    #

    def get_include_directive_file_path(line):



        # It's fine if the line is commented;
        # this would mean that the meta-directive would still generate code,
        # but where the meta-directive is isn't where the code would be inserted at right now.
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

                    break # Python files that are meta-directives should have the meta-header at the top.

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

                    if not re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]*', symbol):
                        assert False, repr(symbol)

                    symbols += [symbol]



                # We're find with duplicate symbols;
                # doesn't really affect anything besides being redundant.

                ports[port_i] = OrdSet(symbols)



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
                            assert False

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
                global_exporter               = has_import_field and not imports,
                body_lines                    = body_lines,
                bytecode_name                 = None,
            )]



    ################################################################################################################################
    #
    # Check consistency of exports and imports.
    #



    if dupes := coalesce((
        (meta_directive.include_directive_file_path, meta_directive)
        for meta_directive in meta_directives
        if meta_directive.include_directive_file_path is not None
    ), find_dupes = True):

        raise MetaError(
            f'# Meta-directives with the same output file path of "{dupes[0].include_directive_file_path}": ' \
            f'[{dupes[0].source_file_path}:{dupes[0].include_directive_line_number}] and ' \
            f'[{dupes[1].source_file_path}:{dupes[1].include_directive_line_number}].'
        )



    if dupes := coalesce((
        (symbol, meta_directive)
        for meta_directive in meta_directives
        for symbol in meta_directive.exports
    ), find_dupes = True):

        raise MetaError(f'# Multiple meta-directives export the symbol "{symbol}".')



    all_exports = OrdSet(
        export
        for meta_directive in meta_directives
        for export         in meta_directive.exports
    )

    for meta_directive in meta_directives:

        for symbol in meta_directive.imports:

            if symbol in meta_directive.exports:
                raise MetaError(f'# Meta-directives exports "{symbol}" but also imports it.')

            if symbol not in all_exports:
                raise MetaError(f'# Meta-directives imports "{symbol}" but no meta-directive exports that.')



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



    # If it's just a bare meta-header, then the meta-directive implicitly imports everything.

    for meta_directive in meta_directives:
        if not meta_directive.exports and not meta_directive.imports and not meta_directive.global_exporter:
            meta_directive.imports = all_exports



    # If the meta-directive explicitly imports nothing, then its exports will
    # globally be implicitly imported into every other meta-directive.

    implicit_global_import = OrdSet(
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
    available_symbols         = OrdSet()

    while remaining_meta_directives:

        for meta_directive_i, meta_directive in enumerate(remaining_meta_directives):



            # This meta-directive doesn't have all of its imports satisfied yet.

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
            raise MetaError(f'# Meta-directive has a circular import dependency.') # TODO Better error message.



    ################################################################################################################################
    #
    # The meta-decorator that handles the the set-up and resolution of a meta-directive's execution.
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
                next(callback_iterator)



            # Meta is special in that it needs to be a global singleton. This is for meta-directives that
            # define functions that use Meta itself to generate code, and that function might be called
            # in a different meta-directive. They all need to refer to the same object, so one singleton
            # must be made for everyone to refer to. Still, checks are put in place to make Meta illegal
            # to use in meta-directives that do not have an associated include-directive.

            function_globals = { 'Meta' : Meta }



            # We deepcopy exported values to be then put in the function's global namespace
            # so that if a meta-directive mutates it for some reason,
            # it'll only be contained within that meta-directive; this isn't really necessary,
            # but since meta-directives are evaluated mostly out-of-order, it helps keep the
            # uncertainty factor lower. This, however, does induce a performance hit if the object
            # is quite large.

            for symbol in meta_directive.imports:
                if isinstance(meta_globals[symbol], types.ModuleType): # Modules are not deepcopy-able.
                    function_globals[symbol] = meta_globals[symbol]
                else:
                    function_globals[symbol] = copy.deepcopy(meta_globals[symbol])



            # Execute the meta-directive.

            Meta._start(meta_directive)
            types.FunctionType(function.__code__, function_globals)()
            Meta._end()



            # Copy the exported symbols into the collective symbol namespace so far.

            for symbol in meta_directive.exports:

                if symbol not in function_globals:
                    raise MetaError(
                        undefined_exported_symbol = symbol,
                        source_file_path          = meta_directive.source_file_path,
                        meta_header_line_number   = meta_directive.meta_header_line_number,
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
                    raise RuntimeError('Callback did not return.')



            # Onto next meta-directive!

            current_meta_directive_index += 1



        return decorator



    ################################################################################################################################
    #
    # Routine to handle exceptions that occured during compilation or execution of meta-directives.
    #

    def diagnose(error):



        # Determine the stack trace.

        stacks = []

        match error:



            # Likely a meta-directive that caused this syntax error;
            # otherwise, probably something else obscure (e.g. meta-directive running `exec` or importing).

            case SyntaxError():

                if not (match := [meta_directive for meta_directive in meta_directives if meta_directive.bytecode_name == error.filename]):
                    raise

                meta_directive, = match

                stacks += [types.SimpleNamespace(
                    file_path     = meta_directive.source_file_path,
                    line_number   = (meta_directive.meta_header_line_number + 1) + error.lineno - meta_directive.body_line_number,
                    function_name = None,
                )]



            # For most errors we can inspect the traceback to show all the levels of function calls.

            case _:



                # Get the tracebacks after we begin executing the meta-directive's Python snippet.

                traces = traceback.extract_tb(sys.exc_info()[2])

                while traces and traces[0].name != '__META_DIRECTIVE__':
                    del traces[0]

                if not traces:
                    raise # Otherwise something else happened outside of the meta-directive...



                # Find each level of the stack; some might be in a meta-directive while others are in a imported module.

                for trace in traces:

                   if match := [meta_directive for meta_directive in meta_directives if meta_directive.bytecode_name == trace.filename]:
                       meta_directive,   = match
                       stack_file_path   = meta_directive.source_file_path
                       stack_line_number = (meta_directive.meta_header_line_number + 1) + trace.lineno - meta_directive.body_line_number
                   else:
                       stack_file_path   = pathlib.Path(trace.filename)
                       stack_line_number = trace.lineno

                   stacks += [types.SimpleNamespace(
                       file_path     = stack_file_path,
                       line_number   = stack_line_number,
                       function_name = '<meta-directive>' if trace.name == '__META_DIRECTIVE__' else trace.name,
                   )]



        # Get the surrounding context of each stack.

        for stack in stacks:
            stack.lines = [
                ((line_i + 1) - stack.line_number, line)
                for line_i, line in enumerate(stack.file_path.read_text().splitlines())
                if abs((line_i + 1) - stack.line_number) <= 4
            ]



        # Log the stack trace.

        log()

        line_number_just = max([0] + [len(str(stack.line_number + stack.lines[-1][0])) for stack in stacks])

        for stack_i, stack in enumerate(stacks):



            # Spacer.

            if stack_i:
                log(' ' * line_number_just + ' .'                           )
                log(' ' * line_number_just + ' . ', end = ''                )
                log('.' * 150                     , ansi = 'fg_bright_black')
                log(' ' * line_number_just + ' .'                           )



            # Show the context.

            log(' ' * line_number_just + ' |')

            for line_delta, line in stack.lines:

                with log(ansi = 'bold' if line_delta == 0 else None): # TODO Allow end = ''.

                    line_number = stack.line_number + line_delta

                    log(f'{str(line_number).rjust(line_number_just)} |', end  = ''                                             )
                    log(f' {line}'                                     , ansi = 'bg_red' if line_delta == 0 else None, end = '')

                    if line_delta == 0:

                        log(f' <- {stack.file_path} : {line_number}', ansi = 'fg_yellow', end = '')

                        if stack.function_name is not None:
                            log(f' : {stack.function_name}', ansi = 'fg_yellow', end = '')

                    log()

            log(' ' * line_number_just + ' |')

        log()



        # User deals with the exception now.

        raise MetaError from error



    ################################################################################################################################
    #
    # Compile each meta-directive to catch any syntax errors.
    #

    for meta_directive in meta_directives:



        # Every meta-directive is executed within a function context wrapped by the decorator.

        meta_code = [
            f'@__META_DECORATOR__(__META_GLOBALS__)',
            f'def __META_DIRECTIVE__():',
        ]



        # List the things that the function is expected to define in the global namespace.

        if meta_directive.exports:
            meta_code += [
                f'',
                f'    global {', '.join(meta_directive.exports)}',
            ]



        # If the #meta directive has no code and doesn't export anything,
        # the function would end up empty, which is invalid Python syntax;
        # having a `pass` is a simple fix for this edge case.

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



        # Compile the meta-directive; this has to be done for each meta-directive individually
        # rather than all together at once because a syntax error can "leak" across multiple
        # meta-directives, to which it's then hard to identify where the exact source of the syntax error is.

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

    try:

        globals = { '__META_DECORATOR__' : __META_DECORATOR__, '__META_GLOBALS__' : {} }

        for meta_directive in meta_directives:

            exec(meta_directive.bytecode, globals, {})

    except Exception as error:
        diagnose(error)
