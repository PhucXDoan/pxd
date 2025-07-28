import pathlib, types, contextlib, re, traceback, builtins, sys, copy
from ..pxd.log   import log
from ..pxd.utils import ljusts, root, deindent, repr_in_c, mk_dict, find_dupe, Record, OrdSet, ErrorLift

# TODO Warn on unused symbols.

class MetaError(Exception):

    def __init__(
        self,
        diagnostic                = None, *,
        undefined_exported_symbol = None,
        source_file_path          = None,
        header_line_number        = None
    ):
        self.diagnostic                = diagnostic
        self.undefined_exported_symbol = undefined_exported_symbol # When a meta-directive doesn't define a symbol it said it'd export.
        self.source_file_path          = source_file_path          # "
        self.header_line_number        = header_line_number        # "

    def __str__(self):
        return self.diagnostic

################################################################ Meta ################################################################

class Meta:

    def __init__(self):
        self.__dict__['include_file_path'] = None


    def _start(self, include_file_path, source_file_path, include_directive_line_number):
        self.__dict__ |= {
            'include_file_path'              : include_file_path,
            'source_file_path'               : source_file_path,
            'include_directive_line_number'  : include_directive_line_number,
            'output'                         : '',
            'indent'                         : 0,
            'within_macro'                   : False,
            'overloads'                      : {},
        }


    def __setattr__(self, key, value):

        if self.__dict__['include_file_path'] is None and key in ('output', 'indent', 'within_macro', 'overloads'):
            raise MetaError(ErrorLift(f'The meta-directive needs to have an include-directive to use Meta.'))

        self.__dict__[key] = value


    def _end(self):

        # No generated code if there's no #include directive.
        if self.include_file_path is None:
            return

        # We need to insert some stuff at the beginning of the file...
        generated   = self.output
        self.output = ''

        # Indicate origin of the meta-directive in the generated output.
        self.line(f'// [{self.source_file_path}:{self.include_directive_line_number}].')

        # Put any overloaded macros first.
        if self.overloads:

            for macro, (all_params, overloading_params) in self.overloads.items():

                nonoverloading_params = [param for param in all_params if param not in overloading_params]

                if nonoverloading_params:
                    nonoverloading_params = f'({', '.join(nonoverloading_params)})'
                else:
                    nonoverloading_params = ''

                self.define(
                    f'{macro}({', '.join(all_params)})',
                    f'_{macro}__##{'##'.join(map(str, overloading_params))}{nonoverloading_params}'
                )

        # Put back the rest of the code that was generated.
        if generated:
            self.line(generated)

        # Spit out the generated code.
        pathlib.Path(self.include_file_path).parent.mkdir(parents=True, exist_ok=True)
        open(self.include_file_path, 'w').write(self.output)


    def line(self, *inputs): # TODO More consistent trimming of newlines.

        if not inputs:
            inputs = ['\n\n\n']

        for input in inputs:

            strings = []

            match input:
                case types.GeneratorType() : strings = list(input)
                case list()                : strings = input
                case str()                 : strings = [input]
                case _                     : raise TypeError('Input type not supported.')

            for string in strings:

                deindented_string = deindent(string)

                for line in deindented_string.splitlines():
                    self.output += (((' ' * 4 * self.indent) + line) + (' \\' if self.within_macro else '')).rstrip() + '\n'


    @contextlib.contextmanager
    def enter(self, header = None, opening = None, closing = None, *, indented = None):

        #
        # Automatically determine the scope parameters.
        #

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

        #
        # Header and opening lines.
        #

        if header is not None:
            self.line(header)

        if indented:
            self.indent += 1

        if opening:
            self.line(opening)

        #
        # Body.
        #

        self.indent += 1
        yield
        self.indent -= 1

        #
        # Closing lines.
        #

        if closing is not None:
            self.line(closing)

        if indented:
            self.indent -= 1

        if defining_macro:
            self.within_macro = False
            self.line()


    def enums(self, *args): return self.__enums(self, *args)
    class __enums:

        def __init__(self, meta, enum_name, underlying_type, members = None, count = True):

            self.meta            = meta
            self.enum_name       = enum_name
            self.underlying_type = underlying_type
            self.members         = members
            self.count           = count

            if self.members is not None:
                self.__exit__() # The list of members are already provided.


        def __enter__(self): # The user provides the list of members in a `with` context.

            if self.members is not None:
                raise ValueError('Cannot use Meta.enums in a with-context when members are already provided: {self.members}.')

            self.members = []
            return self.members


        def __exit__(self, *dont_care_about_exceptions):

            self.members = list(self.members)

            if self.underlying_type is None:
                enum_type = ''
            else:
                enum_type = f' : {self.underlying_type}'

            with self.meta.enter(f'enum {self.enum_name}{enum_type}'):
                for member, ljust_member_name in zip(self.members, ljusts(
                    f'{self.enum_name}_{member[0] if member[0] is not None else 'none'}' if isinstance(member, tuple) else
                    f'{self.enum_name}_{member    if member    is not None else 'none'},'
                    for member in self.members
                )):
                    match member:
                        case (name, value) : self.meta.line(f'{ljust_member_name} = {value},')
                        case  name         : self.meta.line(ljust_member_name)

            # Provide the amount of members; it's its own enumeration so it won't have
            # to be explicitly handled in switch statements. Using a #define would also
            # work, but this could result in a name conflict; making the count be its own
            # enumeration prevents this collision since it's definition is scoped to where
            # it is defined.
            if self.count:
                # TODO: self.meta.line(f'enum{enum_type} {{ {self.enum_name}_COUNT = {len(self.members)} }};')
                # TODO: Using `constexpr` is better here so the comparison `an_enum_member < the_enum_COUNT` can be done
                # without any warnings. Support for `constexpr` might be less than the solution above however,
                # so it'll be good to be able to switch between the two.
                self.meta.line(f'constexpr {self.underlying_type} {self.enum_name}_COUNT = {len(self.members)};')


    def define(self, name, params_or_expansion, expansion=None, do_while=False, **overloading):

        if overloading:

            #
            # Determine if the caller provided parameters.
            #

            if expansion is None:
                raise ValueError('When overloading a macro ("{name}"), a tuple of parameter names and a string for the expansion must be given.')

            params    = params_or_expansion
            expansion = expansion

            if isinstance(params, str): # The parameter-list can just be a single string to represent a single argument.
                params = (params,)
            elif params is not None:
                params = list(params)

            for key in overloading:
                if key not in params:
                    raise ValueError(f'Overloading a macro ("{name}") on the parameter "{key}", but it\'s not in the parameter-list: {params}.')

            #
            # Make note of the fact that there'll be "multiple instances" of the same macro.
            #

            if name in self.overloads:
                if self.overloads[name] != (params, list(overloading.keys())):
                    raise ValueError(f'Cannot overload a macro ("{name}") with differing overloaded parameters.')
            else:
                self.overloads[name] = (params, list(overloading.keys()))


            #
            # Define the macro instance.
            #

            self.define(
                f'_{name}__{'__'.join(map(str, overloading.values()))}',
                [param for param in params if param not in overloading] or None,
                expansion,
            )

        else:

            #
            # Determine if the caller provided parameters.
            #

            if expansion is None:
                params    = None
                expansion = params_or_expansion
            else:
                params    = params_or_expansion
                expansion = expansion

            if isinstance(params, str): # The parameter-list can just be a single string to represent a single argument.
                params = (params,)
            elif params is not None:
                params = list(params)

            expansion = deindent(repr_in_c(expansion))

            if params is None:
                macro = f'{name}'
            else:
                macro = f'{name}({', '.join(params)})'


            # Generate macro that spans multiple lines.
            if '\n' in expansion:

                with self.enter(f'#define {macro}'):

                    # Generate multi-lined macro wrapped in do-while.
                    if do_while:
                        with self.enter('do', '{', '}\nwhile (false)'):
                            self.line(expansion)

                    # Generate unwrapped multi-lined macro.
                    else:
                        self.line(expansion)

            # Generate single-line macro wrapped in do-while.
            elif do_while:
                self.line(f'#define {macro} do {{ {expansion} }} while (false)')

            # Generate unwrapped single-line macro.
            else:
                self.line(f'#define {macro} {expansion}')



    def ifs(self, items, style):

        items = tuple(items)

        def decorator(func):

            for item_i, item in enumerate(items):

                #
                # First iteration of the function should give us the condition of the if-statement.
                #

                iterator = func(item)

                try:
                    condition = next(iterator)
                except StopIteration:
                    raise RuntimeError(ErrorLift("The function didn't yield for the condition of the if-statement."))

                #
                # Then generate the if-statement according to the desired style.
                #

                match item_i, style:
                    case _, 'if'      : entrance = (f'if ({condition})'     , None, None                               )
                    case 0, 'else if' : entrance = (f'if ({condition})'     , None, None                               )
                    case _, 'else if' : entrance = (f'else if ({condition})', None, None                               )
                    case _, '#if'     : entrance = (f'#if {condition}'      , None, None                               )
                    case 0, '#elif'   : entrance = (f'#if {condition}'      , None, '#endif' if len(items) == 1 else '')
                    case _, '#elif'   : entrance = (f'#elif {condition}'    , None, None                               )
                    case _            : raise ValueError(ErrorLift(f'Unknown if-statement style of "{style}".'))

                #
                # Next iteration of the function should generate the code within the if-statement.
                #

                with self.enter(*entrance):

                    stopped = False

                    try:
                        next(iterator)
                    except StopIteration:
                        stopped = True

                    if not stopped:
                        raise RuntimeError(ErrorLift('The function should only yield once to make the if-statement.'))

        return decorator



    def lut(self, table_name, entries):

        # e.g: Meta.lut(table_name, (f(x) for x in xs))
        entries = tuple(entries)


        # If the first element of every entry's field-list is a non-tuple,
        # then we assume that is the index of the entry.
        # e.g:
        #     Meta.lut(table_name, ((
        #         index,
        #         (type, name, value),
        #         (type, name, value),
        #         (type, name, value),
        #     ) for x in xs))
        if all(entry and not isinstance(entry[0], tuple) for entry in entries):
            indices = [repr_in_c(index) for index, *fields in entries]
            entries = [fields           for index, *fields in entries]

        # The entries of the look-up table will be defined in sequential order with no explicit indices.
        # e.g:
        #     Meta.lut(table_name, ((
        #         (type, name, value),
        #         (type, name, value),
        #         (type, name, value),
        #     ) for x in xs))
        else:
            indices = None


        match table_name:

            # If the type for the look-up table's entries is given,
            # then each field won't be specified a type.
            # e.g:
            #     Meta.lut((table_type, table_name), ((
            #         (name, value),
            #         (name, value),
            #         (name, value),
            #     ) for x in xs))
            case (table_type, table_name):

                values = [
                    [f'.{name} = {repr_in_c(value)}' for name, value in entry]
                    for entry in entries
                ]

                field_names_per_entry = [
                    (name for name, value in entry)
                    for entry in entries
                ]


            # If the type for the look-up table's entries is not given,
            # then we'll create the type based on the type of each field.
            # e.g:
            #     Meta.lut(table_name, ((
            #         (type, name, value),
            #         (type, name, value),
            #         (type, name, value),
            #     ) for x in xs))
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

        #
        # Output the look-up table.
        #

        if indices is not None and (dupe := find_dupe(indices)) is not None:
            raise ValueError(ErrorLift(f'Look-up table has duplicate index of "{dupe}".'))

        for field_names in field_names_per_entry:
            if (dupe := find_dupe(field_names)) is not None:
                raise ValueError(ErrorLift(f'Look-up table has an entry with duplicate field of "{dupe}".'))

        lines = ['{ ' + ', '.join(value) + ' },' for value in ljusts(values)]

        if indices is not None:
            lines = [f'[{index}] = {value}' for index, value in zip(ljusts(indices), lines)]

        with self.enter(f'static const {table_type} {table_name}[] ='):
            self.line(lines)



################################################################ Meta-Directive ################################################################

def MetaDirective(**info):
    def decorator(function):
        nonlocal info
        info = Record(info)

        #
        # Start of callback.
        #

        if info.callback is None:
            callback_iterator = None
        else:
            callback_iterator = info.callback(info)
            next(callback_iterator)

        #
        # Determine the global namespace.
        #

        function_globals = {}

        for symbol in info.imports:

            # We have to skip modules since they're not deepcopy-able.
            if isinstance(info.meta_globals[symbol], types.ModuleType):
                function_globals[symbol] = info.meta_globals[symbol]

            # We deepcopy exported values so that if a meta-directive mutates it for some reason,
            # it'll only be contained within that meta-directive; this isn't really necessary,
            # but since meta-directives are evaluated mostly out-of-order, it helps keep the
            # uncertainty factor lower.
            else:
                function_globals[symbol] = copy.deepcopy(info.meta_globals[symbol])

        # Meta is special in that it is the only global singleton. This is for meta-directives that
        # define functions that use Meta itself to generate code, and that function might be called
        # in a different meta-directive. They all need to refer to the same object, so one singleton
        # must be made for everyone to refer to. Still, checks are put in place to make Meta illegal
        # to use in meta-directives that do not have an associated #include.
        function_globals['Meta'] = info.meta_globals['Meta']

        #
        # Execute the meta-directive.
        #

        function_globals['Meta']._start(info.include_file_path, info.source_file_path, info.include_directive_line_number)
        types.FunctionType(function.__code__, function_globals)()
        function_globals['Meta']._end()

        #
        # Copy the exported symbols into the collective namespace.
        #

        for symbol in info.exports:

            if symbol not in function_globals:
                raise MetaError(
                    undefined_exported_symbol = symbol,
                    source_file_path          = info.source_file_path,
                    header_line_number        = info.header_line_number,
                )

            info.meta_globals[symbol] = function_globals[symbol]

        #
        # End of callback.
        #

        if info.callback is not None:

            stopped = False

            try:
                callback_iterator.send(function_globals['Meta'].output)
            except StopIteration:
                stopped = True

            if not stopped:
                raise RuntimeError('Callback did not return.')

    return decorator

################################################################ Meta-Preprocessor ################################################################

def do(*,
    output_dir_path,
    meta_py_file_path = None,
    source_file_paths,
    callback = None,
):

    #
    # Convert to pathlib.Path.
    #

    output_dir_path = pathlib.Path(output_dir_path)

    if meta_py_file_path is None:
        meta_py_file_path = output_dir_path.joinpath('__meta__.py')

    source_file_paths = tuple(map(pathlib.Path, source_file_paths))

    #
    # Get all of the #meta directives.
    #

    meta_directives = []

    def get_ports(string, diagnostic_header): # TODO Instead of diagnostic_header, we should pass in the file path and line number range.

        match string.split(':'):
            case [exports         ] : ports = [exports, None   ]
            case [exports, imports] : ports = [exports, imports]
            case _                  : raise MetaError(f'{diagnostic_header} Too many colons for meta-directive!') # TODO Improve.

        return [
            OrdSet(
                symbol.strip()
                for symbol in port.split(',')
                if symbol.strip() # We'll be fine if there's extra commas; just remove the empty strings.
            ) if port is not None else None for port in ports
        ]

    def breakdown_include_directive_line(line):

        #
        # It's fine if the line is commented.
        #

        line = line.strip()
        if   line.startswith('//'): line = line.removeprefix('//')
        elif line.startswith('/*'): line = line.removeprefix('/*')

        #
        # Check if the line has an include directive.
        #

        if not (line := line.strip()).startswith('#'):
            return None
        line = line.removeprefix('#')

        if not (line := line.strip()).startswith('include'):
            return None
        line = line.removeprefix('include')

        if not (line := line.strip()):
            return None

        if (end_quote := {
            '<' : '>',
            '"' : '"',
        }.get(line[0], None)) is None:
            return None

        if (length := line[1:].find(end_quote)) == -1:
            return None

        include_file_path = pathlib.Path(output_dir_path, line[1:][:length])

        return include_file_path

    for source_file_path in source_file_paths:

        remaining_lines       = open(source_file_path, 'rb').read().decode('UTF-8').splitlines()
        remaining_line_number = 1

        # Python file that might just be a big meta-directive.
        if source_file_path.suffix == '.py':

            while remaining_lines:

                #
                # See if there's an #include directive.
                #

                include_line = None

                if (include_file_path := breakdown_include_directive_line(remaining_lines[0])) is not None:
                    include_line           = remaining_lines[0 ]
                    remaining_lines        = remaining_lines[1:]
                    remaining_line_number += 1

                #
                # See if there's a #meta.
                #

                header_line            = remaining_lines[0]
                header_line_number     = remaining_line_number
                remaining_lines        = remaining_lines[1:]
                remaining_line_number += 1

                diagnostic_header  = ''
                diagnostic_header  = '#' * 64 + '\n'
                diagnostic_header += f'{header_line.strip()}\n'
                diagnostic_header += '#' * 64 + '\n'
                diagnostic_header += f'# [{source_file_path}:{header_line_number}]'

                tmp = header_line
                tmp = tmp.strip()
                if tmp.startswith('#meta'):
                    tmp = tmp.removeprefix('#meta')
                    tmp = tmp.strip()

                    exports, imports = get_ports(tmp, diagnostic_header)

                    meta_directives += [types.SimpleNamespace(
                        source_file_path   = source_file_path,
                        header_line_number = header_line_number,
                        include_file_path  = include_file_path,
                        exports            = exports,
                        imports            = imports,
                        lines              = remaining_lines,
                    )]

                    break # The rest of the file is the entire #meta directive.

                elif tmp:
                    break # First non-empty line is not a #meta directive.

        # Assuming C file.
        else:

            while remaining_lines:

                #
                # See if there's an #include directive.
                #

                include_line = None

                if (include_file_path := breakdown_include_directive_line(remaining_lines[0])) is not None:
                    include_line           = remaining_lines[0 ]
                    remaining_lines        = remaining_lines[1:]
                    remaining_line_number += 1

                #
                # See if there's a block comment with #meta.
                #

                if not remaining_lines:
                    continue

                header_line            = remaining_lines[0]
                header_line_number     = remaining_line_number
                remaining_lines        = remaining_lines[1:]
                remaining_line_number += 1

                diagnostic_header  = ''
                diagnostic_header  = '#' * 64 + '\n'
                if include_line is not None:
                    diagnostic_header += f'{include_line.strip()}\n'
                diagnostic_header += f'{header_line.strip()}\n'
                diagnostic_header += '#' * 64 + '\n'
                diagnostic_header += f'# [{source_file_path}:{header_line_number}]'

                tmp = header_line
                tmp = tmp.strip()
                if tmp.startswith('/*'):
                    tmp = tmp.removeprefix('/*')
                    tmp = tmp.strip()

                    if tmp.startswith('#meta'):
                        tmp = tmp.removeprefix('#meta')
                        tmp = tmp.strip()

                        exports, imports = get_ports(tmp, diagnostic_header)

                        #
                        # Get lines of the block comment.
                        #

                        lines  = []
                        ending = -1

                        while ending == -1:

                            # Pop a line of the block comment.
                            if not remaining_lines:
                                raise MetaError(f'{diagnostic_header} Meta-directive without a closing `*/`!')
                            line                   = remaining_lines[0]
                            remaining_lines        = remaining_lines[1:]
                            remaining_line_number += 1

                            # Truncate up to the end of the block comment.
                            if (ending := line.find('*/')) != -1:
                                line = line[:ending]

                            # Got line!
                            line   = line.rstrip()
                            lines += [line]

                        lines = deindent(lines, remove_leading_newline = False, single_line_comment = '#')

                        meta_directives += [types.SimpleNamespace(
                            source_file_path   = source_file_path,
                            header_line_number = header_line_number,
                            include_file_path  = include_file_path,
                            exports            = exports,
                            imports            = imports,
                            lines              = lines,
                        )]

    #
    # Process the meta-directives' parameters.
    #

    include_collisions = {}
    for meta_directive in meta_directives:
        if meta_directive.include_file_path is not None:
            if (collision := include_collisions.get(meta_directive.include_file_path, None)) is None:
                include_collisions[meta_directive.include_file_path] = meta_directive
            else:
                raise MetaError( # TODO Improve.
                    f'# Meta-directives with the same output file path of "{meta_directive.include_file_path}": ' \
                    f'[{meta_directive.source_file_path}:{meta_directive.header_line_number - 1}] and ' \
                    f'[{collision     .source_file_path}:{collision     .header_line_number - 1}].'
                )

    all_exports = {}

    for meta_directive in meta_directives:
        for symbol in meta_directive.exports:

            if symbol in all_exports:
                raise MetaError(f'# Multiple meta-directives export the symbol "{symbol}".') # TODO Better error message.

            all_exports[symbol] = meta_directive

    for meta_directive in meta_directives:
        if meta_directive.imports is not None:
            for symbol in meta_directive.imports:

                if symbol not in all_exports:
                    raise MetaError(f'# Meta-directives imports "{symbol}" but no meta-directive exports that.') # TODO Better error message.

                if all_exports[symbol] == meta_directive:
                    raise MetaError(f'# Meta-directives exports "{symbol}" but also imports it.') # TODO Better error message.

    for meta_directive in meta_directives:

        # If no exports/imports are explicitly given,
        # then the meta-directive implicitly imports everything.
        if not meta_directive.exports and not meta_directive.imports:
            meta_directive.imports = OrdSet(all_exports.keys())

    #
    # Sort the #meta directives.
    #

    # Meta-directives with empty imports are always done first,
    # because their exports will be implicitly imported to all the other meta-directives.
    remaining_meta_directives = [d for d in meta_directives if d.imports != {}]
    meta_directives           = [d for d in meta_directives if d.imports == {}]
    implicit_symbols          = OrdSet(symbol for meta_directive in meta_directives for symbol in meta_directive.exports)
    current_symbols           = OrdSet(implicit_symbols)

    while remaining_meta_directives:

        # Find next meta-directive that has all of its imports satisfied.
        next_directivei, next_directive = next((
            (i, meta_directive)
            for i, meta_directive in enumerate(remaining_meta_directives)
            if meta_directive.imports is None or all(symbol in current_symbols for symbol in meta_directive.imports)
        ), (None, None))

        if next_directivei is None:
            raise MetaError(f'# Meta-directive has a circular import dependency.') # TODO Better error message.

        current_symbols |=  next_directive.exports
        meta_directives += [next_directive]
        del remaining_meta_directives[next_directivei]

    #
    # Generate the Meta Python script.
    #

    output_dir_path.mkdir(parents=True, exist_ok=True)

    meta_py = []

    # Additional context.
    for meta_directive_i, meta_directive in enumerate(meta_directives):

        if meta_directive.include_file_path is None:
            include_file_path             = None
            include_directive_line_number = None
        else:
            include_file_path             = f"r'{meta_directive.include_file_path}'"
            include_directive_line_number =      meta_directive.header_line_number - 1

        if meta_directive.imports == OrdSet():
            imports = {} # The meta-directive explicitly has no imports.
        else:
            imports = (meta_directive.imports or OrdSet()) | implicit_symbols # The meta-directive lists its imports or have them be implicit given.

        exports = ', '.join(map(repr, meta_directive.exports))
        imports = ', '.join(map(repr, imports        ))

        meta_py += deindent(f'''
            @MetaDirective(
                index                         = {meta_directive_i},
                source_file_path              = r'{meta_directive.source_file_path}',
                header_line_number            = {meta_directive.header_line_number},
                include_file_path             = {include_file_path            },
                include_directive_line_number = {include_directive_line_number},
                exports                       = [{exports}],
                imports                       = [{imports}],
                meta_globals                  = __META_GLOBALS__,
                **__META_SHARED__
            )
            def __META__():
        ''').splitlines()

        # List the things that the function is expected to define in the global namespace.
        if meta_directive.exports:
            meta_py += [f'    global {', '.join(meta_directive.exports)}']

        # If the #meta directive has no code and doesn't export anything,
        # the function would end up empty, which is invalid Python syntax;
        # having a `pass` is a simple fix for this edge case.
        if not any(line.strip() and line.strip()[0] != '#' for line in meta_directive.lines) and not meta_directive.exports:
            meta_py += ['    pass']

        # Inject the #meta directive's Python snippet.
        meta_py += ['']
        meta_directive.meta_py_line_number = len(meta_py) + 1
        for line in meta_directive.lines:
            meta_py += [f'    {line}' if line else '']
        meta_py += ['']

    meta_py = '\n'.join(meta_py) + '\n'

    # Output the Meta Python script for debuggability.
    pathlib.Path(meta_py_file_path).parent.mkdir(parents=True, exist_ok=True)
    open(meta_py_file_path, 'w').write(meta_py)

    #
    # Execute the Meta Python file.
    #

    try:
        exec(
            meta_py,
            {
                'MetaDirective' : MetaDirective,
                '__META_GLOBALS__' : {
                    'Meta' : Meta(),
                },
                '__META_SHARED__' : {
                    'callback'        : callback,
                    'meta_directives' : meta_directives,
                },
            },
            {},
        )

    except Exception as err:

        #
        # Get the file paths, line numbers, and code to show for the diagnostic.
        #

        stacks = []

        match err:

            # Syntax errors are tricky;
            # it's not possible to determine which meta-directive is causing the syntax error,
            # because the error might be spilling across multiple meta-directives.
            case builtins.SyntaxError() | builtins.IndentationError():
                raise err from err

            # Errors that happen outside of the execution of the meta-directive. TODO Questionable.
            case meta_err if isinstance(meta_err, MetaError) and meta_err.undefined_exported_symbol is not None:
                stacks += [types.SimpleNamespace(
                    file_path   = root(err.source_file_path),
                    line_number = err.header_line_number,
                    func_name   = '<meta-directive>',
                )]

            # Errors that happen during the execution of the meta-directive.
            case _:

                tbs = traceback.extract_tb(sys.exc_info()[2])

                while tbs and tbs[0].name != '__META__':
                    del tbs[0] # We only care what happens after we begin executing the meta-directive's Python snippet.

                if not tbs:
                    raise err from err

                for tb in tbs:

                    file_path   = tb.filename
                    line_number = tb.lineno

                    if file_path == '<string>':

                        # This likely means the error happened when we executed `__meta__.py`,
                        # so we adjust the reported file path and line number to be at the original meta-directive.

                        err_dir = next(
                            dir
                            for dir in meta_directives
                            if 0 <= (line_number - dir.meta_py_line_number) <= len(dir.lines)
                        )

                        file_path   = err_dir.source_file_path
                        line_number = err_dir.header_line_number + (line_number - err_dir.meta_py_line_number) + 1

                    stacks += [types.SimpleNamespace(
                        file_path   = root(file_path),
                        line_number = line_number,
                        func_name   = '<meta-directive>' if tb.name == '__META__' else tb.name,
                    )]

        for stack in stacks:
            stack.lines = [
                (line_i + 1 - stack.line_number, line)
                for line_i, line in enumerate(open(stack.file_path).read().splitlines())
                if abs(line_i + 1 - stack.line_number) <= 4
            ]

        if err.args and isinstance(err.args[0], ErrorLift):
            stacks = stacks[:-1]

        if isinstance(err, MetaError) and not err.args and not err.undefined_exported_symbol: # Meta-directive logged the error.
            raise MetaError() from err

        #
        # Log the diagnostics.
        #

        log()

        line_number_just = max(0, *(len(str(stack.line_number + stack.lines[-1][0])) for stack in stacks))

        for stack_i, stack in enumerate(stacks):

            log(' ' * line_number_just + ' .')
            log(' ' * line_number_just + ' . ', end = '')
            log('.' * 150, ansi = 'fg_bright_black')
            log(' ' * line_number_just + ' .')
            log(' ' * line_number_just + ' |')

            for line_delta, line in stack.lines:

                line_number = stack.line_number + line_delta

                with log(ansi = 'bold' if line_delta == 0 else None):

                    log(
                        f'{str(line_number).rjust(line_number_just)} |',
                        end  = '',
                    )
                    log(
                        f' {line}',
                        ansi = 'bg_red' if line_delta == 0 else None,
                        end  = '',
                    )

                    if line_delta == 0:
                        log(f' <- {stack.file_path} : {line_number} : {stack.func_name}', ansi = 'fg_yellow', end = '')

                    log()

            log(' ' * line_number_just + ' |')

        log()

        with log(ansi = 'fg_red'):

            match err:

                case builtins.NameError():
                    log(f'[ERROR] Name exception.')
                    log(f'        > {str(err).removesuffix('.')}.') # TODO Better error message when NameError refers to an export.

                case builtins.AttributeError():
                    log(f'[ERROR] Attribute exception.')
                    log(f'        > {str(err).removesuffix('.')}.')

                case builtins.KeyError():
                    log(f'[ERROR] Key exception.')
                    log(f'        > {str(err)}.')

                case builtins.ValueError():
                    log(f'[ERROR] Value exception.')
                    log(f'        > {str(err).removesuffix('.')}.')

                case builtins.NotImplementedError():
                    log(f'[ERROR] Unimplemented codepath exception.')
                    log(f'        > {str(err).removesuffix('.')}.')

                case builtins.RuntimeError():
                    log(f'[ERROR] Runtime exception.')
                    log(f'        > {str(err).removesuffix('.')}.')

                case builtins.AssertionError():
                    log(f'[ERROR] Assert exception.')
                    if err.args:
                        log(f'        > {err.args[0]}')

                case MetaError():
                    if err.undefined_exported_symbol is not None:
                        log(f'[ERROR] Meta-directive did not define "{err.undefined_exported_symbol}".')
                    else:
                        log(f'[ERROR] Meta-preprocessor exception.')
                        log(f'        > {str(err).removesuffix('.')}.')

                case _:
                    log(f'[ERROR] {type(err)}')
                    log(f'        > {err}')

        raise MetaError() from err
