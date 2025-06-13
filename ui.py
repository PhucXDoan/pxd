import types, inspect, builtins, collections, enum, copy
from ..pxd.log import log, did_you_mean

# TODO Overriding subcommand names should be first verified.

def factory(desc, *, name = None):

    def decorator(func):

        # @/`Overriding Subcommand Names`.
        func.name = func.__name__ if name is None else name

        # Save the description string so it can be used later when it is added to a UI.
        func.desc = desc

        # Mark the function as being processed by the factory.
        func.decorated_by_factory = True

        return func

    return decorator

class UI:

    ################################################################ Helpers ################################################################

    def __is_enum(x):
        return isinstance(x, type) and issubclass(x, enum.Enum)

    ################################################################ Constructor ################################################################

    def __init__(self, name, desc, subcmd_hook = None):

        self.name        = name
        self.desc        = desc
        self.subcmd_hook = subcmd_hook
        self.subcmds     = {}

        # TODO Allow user to override the help subcommand?
        # TODO How to handle descriptions that need updating?.
        @self(f'Show usage of "{self.name}"; use "{self.name} help all" to show more detailed information.')
        def help(
            subcommand_name : (str, 'Name of subcommand to show information on.') = None,
            *,
            show_subcmds        = True,
            prev_uis            = [],
            exclude_help_subcmd = False,
        ):

            invocation = f'> {' '.join(ui.name for ui in [*prev_uis, self])}'

            ################ Subcommand Help ################

            def log_subcmd(subcmd, *, verbose, emphasized):

                # For a subcommand that's just another UI, we just rely on its "help" subcommand.
                if isinstance(subcmd, UI):
                    subcmd.help(
                        subcommand_name     = 'all' if verbose else None,
                        show_subcmds        = verbose,
                        prev_uis            = [*prev_uis, self],
                        exclude_help_subcmd = subcommand_name != subcmd.name,
                    )
                    return

                # Determine the string format of the parameters.

                params = [
                    types.SimpleNamespace(
                        **param.__dict__,
                        str = param.repr
                    )
                    for param in subcmd.params
                ]

                for param in params:

                    if param.flag and param.type != bool:
                        param.str = f'{param.str}=...'

                    param.str = f'({param.str})'

                    if not param.has_dflt:
                        param.str = f'*{param.str}'

                # Block-typed help hooks will log its section on its own.
                if subcmd.help_hook_type == 'block' and verbose:
                    subcmd.func(
                        help_hook = True,
                        **{ param.name : None for param in params }
                    )
                    return

                # Otherwise, we auto-generate most of the help information for the subcommand.

                log(
                    f'{invocation} {subcmd.name}{''.join(f' {param.str}' for param in params)}',
                    ansi = ('bold', 'underline') if emphasized else None
                )
                log(subcmd.desc)

                if not verbose:
                    return # Don't overwhelm the user with information.

                with log(indent = True):

                    for param in params:

                        log()
                        log(f'{param.str} {param.desc}')

                        with log(indent = True):

                            # Parameter default value if exist.
                            if param.has_dflt:
                                match param.dflt:
                                    case str(): dflt_str = f'"{param.dflt}"'
                                    case _    : dflt_str =  f'{param.dflt}'
                                log(f'= {dflt_str}')

                            match param.type:

                                # Nothing particular to do.
                                case builtins.str | builtins.int | builtins.bool:
                                    pass

                                # List the options.
                                case list():
                                    for option in param.type:
                                        log(f'- {option}')

                                # List the options.
                                case enum if UI.__is_enum(enum):
                                    for option in param.type:
                                        log(f'- {option.name}')

                                # Not implemented yet.
                                case _:
                                    raise RuntimeError(
                                        f'In subcommand "{subcmd.func.__name__}", '
                                        f'parameter "{param.name}" has a type of "{param.type}"; '
                                        f'the "help" subcommand doesn\'t know how to properly format parameters of this type yet.'
                                    )

                # The subcommand can also provide additional help information.

                match subcmd.help_hook_type:

                    case None:
                        pass

                    case 'extend':
                        with log(indent = True):
                            log()
                            subcmd.func(
                                help_hook = True,
                                **{ param.name : None for param in params }
                            )

                    case _:
                        raise RuntimeError(
                            f'Subcommand "{subcmd.name}" is defined with a help hook, '
                            f'but the "help_hook" parameter annotated with "{subcmd.help_hook_type}" '
                            f'which is not a recognized format type.' # TODO List options.
                        )

            ################ UI Help ################

            if subcommand_name is None or subcommand_name == 'all':

                emphasized = (subcommand_name == 'all')

                log(
                    f'{invocation} [subcommand] (arguments...)',
                    ansi = ('bold', 'underline') if emphasized else None
                )
                log(self.desc)

                if show_subcmds:
                    for subcmd_name, subcmd in sorted(
                        self.subcmds.items(),
                        key = lambda key_value: key_value[0] == 'help'
                        # Put the "help" subcommand last so it'd be the
                        # first thing that the user will see near the shell cursor.
                    ):

                        if exclude_help_subcmd and subcmd_name == 'help':
                            continue

                        with log(indent = True):
                            log()
                            log_subcmd(
                                subcmd,
                                verbose    = emphasized,
                                emphasized = emphasized,
                            )

            else: # Show help information for a specific subcommand.

                if subcommand_name not in self.subcmds:
                    self.help(prev_uis = prev_uis)
                    log()
                    did_you_mean(
                        f'No subcommand goes by the name "{subcommand_name}"; see list of subcommands above.',
                        subcommand_name,
                        (*self.subcmds.keys(), 'all'),
                        tag  = '[ERROR]',
                        ansi = 'fg_red',
                    )
                    return 1

                log_subcmd(
                    self.subcmds[subcommand_name],
                    verbose    = True,
                    emphasized = False,
                )

        self.help = help

    ################################################################ Registration ################################################################

    def __call__(self, obj, *, name = None):

        ################ Registration Decorator ################

        def decorator(func):

            if name is not None:
                func_name = name          # @/`Overriding Subcommand Names`.
            elif hasattr(func, 'name'):
                func_name = func.name     # The function was already decorated with @factory.
            else:
                func_name = func.__name__ # In most cases, we just use the decorated function's name as the subcommand name.

            #
            # Verify the syntax of the decorated function's parameter-list.
            #

            argspec = inspect.getfullargspec(func)

            if argspec.varargs is not None:
                raise RuntimeError(
                    f'Subcommand "{func_name}" is defined using the variadic argument `*{argspec.varargs}`; '
                    f'this syntax is currently illegal for defining subcommands.'
                )

            if argspec.varkw is not None:
                raise RuntimeError(
                    f'Subcommand "{func_name}" is defined using the variadic keyword-argument `**{argspec.varkw}`; '
                    f'this syntax is currently illegal for defining subcommands.'
                )

            if 'help_hook' in argspec.args and 'help_hook' not in argspec.annotations:
                raise RuntimeError(
                    f'Subcommand "{func_name}" is defined with a help hook, '
                    f'but the "help_hook" parameter is unannotated; '
                    f'it should be annotated with a string indicating the format type of help hook.' # TODO Say the options.
                )

            if 'help_hook' in argspec.args and len(argspec.defaults or []) == len(argspec.args):
                raise RuntimeError(
                    f'Subcommand "{func_name}" is defined with a help hook, '
                    f'but the "help_hook" parameter has a default value; is this a mistake?'
                )

            if unannotated := [arg for arg in argspec.args if arg not in argspec.annotations and arg != 'help_hook']:
                raise RuntimeError(
                    f'In subcommand "{func_name}", '
                    f'parameter "{unannotated[0]}" needs to be annotated with `(type, description)`.'
                )

            if 'help_hook' in argspec.args and argspec.args[0] != 'help_hook':
                raise RuntimeError(
                    f'In the definition of subcommand "{func_name}", '
                    f'parameter "help_hook" should be first in the parameter-list.'
                )

            #
            # Parse the parameters.
            #

            params = [
                types.SimpleNamespace(
                    name = name,
                    type = type_desc[0],
                    desc = type_desc[1],
                )
                for name, type_desc
                in argspec.annotations.items()
                if name != 'help_hook'
            ]

            for param in params:

                # Determine default value.

                defaults       = argspec.defaults or []
                defaults_i     = argspec.args.index(param.name) - len(argspec.args) + len(defaults)
                param.has_dflt = defaults_i >= 0
                param.dflt     = defaults[defaults_i] if param.has_dflt else None

                # Determine type.

                if param.type == bool:
                    param.type = (bool, 'flag') # Boolean parameters are flags automatically.

                match param.type:

                    case (actual_type, 'flag'):
                        param.type = actual_type
                        param.flag = True

                    case actual_type:
                        param.type = actual_type
                        param.flag = False

                # Check type.

                match param.type:

                    case builtins.str | builtins.int | builtins.bool : pass
                    case enum if UI.__is_enum(enum)                  : pass

                    case list():
                        if (duplicates := [
                            option
                            for option, count in dict(collections.Counter(param.type)).items()
                            if count >= 2
                        ]):
                            raise RuntimeError(
                                f'In subcommand "{func_name}", '
                                f'parameter "{param.name}" has the option "{duplicates[0]}" listed more than once.'
                            )

                    case _:
                        raise RuntimeError(
                            f'In subcommand "{func_name}", '
                            f'parameter "{param.name}" has a type of "{param.type}"; '
                            f'subcommands cannot be defined with parameters of this type yet.'
                        )

                # Make the user-friendly parameter name.

                param.repr = param.name.replace('_', '-')

                if param.flag:
                    param.repr = f'--{param.repr}'

            #
            # Save the function.
            #

            subcmd_name = func_name.replace('_', '-')

            if subcmd_name in self.subcmds:
                raise RuntimeError(f'Subcommand "{func_name}" is already defined.')

            self.subcmds[subcmd_name] = types.SimpleNamespace(
                name            = subcmd_name,
                desc            = '\n'.join(line.strip() for line in subcmd_desc.strip().splitlines()),
                func            = func,
                params          = params,
                help_hook_type  = argspec.annotations['help_hook'] if 'help_hook' in argspec.args else None,
            )

            return func

        ################ Subcommand Registration ################

        match obj:

            # The subcommand is being defined using a `def` with a decorator.
            case subcmd_desc if isinstance(subcmd_desc, str):
                return decorator

            # The subcommand is a function that was processed by @factory,
            # so we invoke the decorator directly ourselves.
            case func if hasattr(func, 'decorated_by_factory'):
                subcmd_desc = func.desc
                return decorator(func)

            # The subcommand is another UI with its own set of subcommands.
            case ui if isinstance(ui, UI):

                if ui.name in self.subcmds:
                    raise RuntimeError(f'Subcommand "{func_name}" is already defined.')

                self.subcmds[ui.name] = ui

            # Not implemented yet.
            case _:
                raise RuntimeError(f'Not sure how to register "{obj}" as a subcommand.')

    ################################################################ Invoke ################################################################

    def invoke(self, given, *, prev_uis = []):

        given = list(given)

        if not given:
            self.help( # No subcommand provided, so just show list of subcommands.
                subcommand_name = None,
                prev_uis        = prev_uis,
            )
            return 0

        #
        # Find the subcommand.
        #

        given_subcmd_name, *given_subcmd_args = given

        if (given_subcmd := self.subcmds.get(given_subcmd_name, None)) is None:
            self.help(prev_uis = prev_uis)
            log()
            did_you_mean(
                f'Unrecognized subcommand "{given_subcmd_name}"; see list of subcommands above.',
                given_subcmd_name,
                self.subcmds.keys(),
                tag  = '[ERROR]',
                ansi = 'fg_red',
            )
            return 1

        #
        # If the subcommand is another UI, pass on the arguments.
        #

        if isinstance(given_subcmd, UI):

            hook_iterator = self.subcmd_hook(given_subcmd_name) if self.subcmd_hook is not None else None

            if hook_iterator is not None:
                next(hook_iterator, None)

            exit_code = given_subcmd.invoke(
                given_subcmd_args,
                prev_uis = [*prev_uis, self],
            )

            if hook_iterator is not None:
                next(hook_iterator, None)

            return 0 if exit_code is None else exit_code

        #
        # Ready to process the parameters and arguments.
        #

        given_subcmd_args = [
            types.SimpleNamespace(
                processed = False,
                value     = arg,
            )
            for arg in given_subcmd_args
        ]

        params = [
            types.SimpleNamespace(
                **param.__dict__,
                has_value = False,
                value     = None,
            )
            for param in given_subcmd.params
        ]

        def parse(param, arg):

            if param.flag:

                # Boolean flags are special in that they don't need a RHS.
                if arg.value == param.repr and param.type == bool:
                    param.value     = True
                    param.has_value = True
                    return 0

                # All other flags need an explicit assignment.
                if arg.value == param.repr:
                    self.help(
                        subcommand_name = given_subcmd_name,
                        prev_uis        = prev_uis,
                    )
                    with log(ansi = 'fg_red'):
                        log()
                        log(
                            f'[ERROR] Parameter "{param.repr}" needs to be given a value; '
                            f'see subcommand help above.'
                        )
                    return 1

                # Make sure the argument flag actually corresponds to this parameter.
                if not arg.value.startswith(substr := f'{param.repr}='):
                    return 0

                # Get RHS for parsing.
                value = arg.value.removeprefix(substr)

            else:

                # Parse as-is.
                value = arg.value

            match param.type:

                # Argument should be a string.
                case builtins.str:
                    param.value     = value
                    param.has_value = True

                # Argument should be an integer.
                case builtins.int:

                    try:
                        param.value     = int(value)
                        param.has_value = True

                    except ValueError as err:
                        self.help(
                            subcommand_name = given_subcmd_name,
                            prev_uis        = prev_uis,
                        )
                        with log(ansi = 'fg_red'):
                            log()
                            log(
                                f'[ERROR] Parameter "{param.repr}" given malformed integer "{value}"; '
                                f'see subcommand help above.'
                            )
                        return 1

                # Argument should something that can be intepreted as a boolean.
                case builtins.bool:

                    FALSY  = ('0', 'f', 'n', 'no' , 'false')
                    TRUTHY = ('1', 't', 'y', 'yes', 'true' )

                    if value.lower() in FALSY:
                        param.value     = False
                        param.has_value = True

                    elif value.lower() in TRUTHY:
                        param.value     = True
                        param.has_value = True

                    else:
                        self.help(
                            subcommand_name = given_subcmd_name,
                            prev_uis        = prev_uis,
                        )
                        with log(ansi = 'fg_red'):
                            log()
                            log(f'[ERROR] Boolean flag "{param.repr}" assigned an unrecognized value of "{value}".')
                            log(f'        Truthy values are : {', '.join(f'"{x}"' for x in TRUTHY if x)}.')
                            log(f'        Falsy  values are : {', '.join(f'"{x}"' for x in FALSY      )}.')
                            log(f'        Values are case-insensitive.')
                        return 1

                # Argument should be one of many options.
                case options if (
                    isinstance(options, list) or
                    UI.__is_enum(options)
                ):

                    if UI.__is_enum(options):
                        options = { option.name : option for option in options }
                    else:
                        options = { str(option) : option for option in options }

                    if value not in options:
                        self.help(
                            subcommand_name = given_subcmd_name,
                            prev_uis        = prev_uis,
                        )
                        log()
                        did_you_mean(
                            f'Parameter "{param.repr}" given unrecognized option "{value}"; '
                            f'see subcommand help above.',
                            value,
                            options.keys(),
                            tag  = '[ERROR]',
                            ansi = 'fg_red',
                        )
                        return 1

                    param.value     = options[value]
                    param.has_value = True

                # Unimplemented parameter type.
                case _:
                    raise RuntimeError(
                        f'In subcommand "{given_subcmd_name}", '
                        f'parameter "{param.name}" has a type of "{param.type}"; '
                        f'parsing for this type is not yet supported.'
                    )

        #
        # Process given arguments that are flags.
        #

        for arg in given_subcmd_args:

            if arg.processed:
                continue

            if not arg.value.startswith('--'):
                continue

            for param in params:

                if param.has_value:
                    continue

                if not param.flag:
                    continue

                if exit_code := parse(param, arg):
                    return exit_code

                if param.has_value:
                    arg.processed = True
                    break

            else:

                flag = arg.value.split('=', 1)[0]

                self.help(
                    subcommand_name = given_subcmd_name,
                    prev_uis        = prev_uis,
                )
                log()
                did_you_mean(
                    f'Unrecognized flag "{flag}"; see subcommand help above.',
                    flag,
                    (param.repr for param in params if param.type == bool),
                    tag  = '[ERROR]',
                    ansi = 'fg_red',
                )
                return 1

        #
        # Process the rest of the arguments.
        #

        for arg in given_subcmd_args:

            if arg.processed:
                continue

            for param in params:

                if param.has_value:
                    continue

                if exit_code := parse(param, arg):
                    return exit_code

                if param.has_value:
                    arg.processed = True
                    break

            else:
                self.help(
                    subcommand_name = given_subcmd_name,
                    prev_uis        = prev_uis,
                )
                with log(ansi = 'fg_red'):
                    log()
                    log(
                        f'[ERROR] Not sure what to do with the given argument "{arg.value}"; '
                        f'see subcommand help above.'
                    )
                return 1

        #
        # Ensure each parameter and argument is accounted for.
        #

        for param in params:

            if param.has_value:
                continue

            if not param.has_dflt:
                self.help(
                    subcommand_name = given_subcmd_name,
                    prev_uis        = prev_uis,
                )
                with log(ansi = 'fg_red'):
                    log()
                    log(
                        f'[ERROR] Subcommand missing required parameter "{param.repr}"; '
                        f'see subcommand help above.'
                    )
                return 1

            param.value = param.dflt

        #
        # Execute the subcommand.
        #

        func_kwargs   = { param.name : param.value for param in params }
        hook_iterator = self.subcmd_hook(given_subcmd_name) if self.subcmd_hook is not None else None

        if given_subcmd.help_hook_type:
            func_kwargs |= { 'help_hook' : False }

        if given_subcmd.func == self.help: # TODO Hacky. We need a better way to do this.
            func_kwargs |= { 'prev_uis' : prev_uis }

        if hook_iterator is not None:
            next(hook_iterator, None)

        exit_code = given_subcmd.func(**func_kwargs)

        if hook_iterator is not None:
            next(hook_iterator, None)

        return 0 if exit_code is None else exit_code

################################################################ Notes ################################################################

# @/`Overriding Subcommand Names`:
# If "name" is provided, then use that instead of
# the decorated function's name; this is to allow
# subcommand names determined by a string variable
# at runtime instead of fixed at parse time when
# using "def".
