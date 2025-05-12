#!/usr/bin/env python3
import pathlib, types, contextlib, re, traceback, builtins, sys, copy

################################################################ Helper Functions. ################################################################

def deindent(lines_or_a_string):

	if isinstance(lines_or_a_string, str):
		# Get the lines.
		lines = lines_or_a_string.splitlines()
	else:
		# Lines already given.
		lines = lines_or_a_string


	# Remove leading newlines.
	while lines and not lines[0]:
		del lines[0]

	# Remove trailing newlines.
	while lines and not lines[-1]:
		del lines[-1]

	# Deindent the lines.
	global_indent = None
	for linei, line in enumerate(lines):

		# Determine line's indent level.
		line_indent = len(line) - len(line.lstrip('\t'))

		# Determine the whole text's indent level based on the first line with actual text.
		if global_indent is None and line.strip():
			global_indent = line_indent

		# Set indents appropriately.
		lines[linei] = line.removeprefix('\t' * min(line_indent, global_indent or 0))


	if isinstance(lines_or_a_string, str):
		# Give back the modified string.
		return '\n'.join(lines)
	else:
		# Give back the modified lines.
		return lines


def cstr(x):
	match x:
		case bool  () : return str(x).lower()
		case float () : return str(int(x) if x.is_integer() else x)
		case _        : return str(x)


class Obj:

	def __init__(self, value=None, **fields):

		if value is not None and fields:
			raise ValueError('Obj should either initialized from a value or by keyword arguments.')

		match value:
			case None   : key_values = fields.items()
			case dict() : key_values = value.items()
			case _      : raise TypeError(f"Can't make an Obj from a {type(value)}: {value}.")

		for key, value in key_values:
			self.__dict__[key] = value


	def __getattr__(self, key):
		raise AttributeError(f'No field (.{key}) to read.')


	def __setattr__(self, key, value):
		if key in self.__dict__:
			self.__dict__[key] = value
		else:
			raise AttributeError(f'No field (.{key}) to write.')


	def __getitem__(self, key):
		if key in self.__dict__:
			return self.__dict__[key]
		else:
			raise KeyError(f'No field ["{key}"] to read.')


	def __setitem__(self, key, value):
		if key in self.__dict__:
			self.__dict__[key] = value
			return value
		else:
			raise KeyError(f'No field ["{key}"] to write.')


	def __iter__(self):
		for name, value in self.__dict__.items():
			yield (name, value)


	def __repr__(self):
		return f'Obj({ ', '.join(f'{k}={v}' for k, v in self) })'


	def __contains__(self, key):
		return key in self.__dict__


class Record:

	def __init__(self, value=None, **fields):

		if value is not None and fields:
			raise ValueError('Record should either initialized from a value or by keyword arguments.')

		match value:
			case None   : key_values = fields.items()
			case dict() : key_values = value.items()
			case _      : raise TypeError(f"Can't make a Record from a {type(value)}: {value}.")

		for key, value in key_values:
			self.__dict__[key] = value


	def __getattr__(self, key):
		raise AttributeError(f'No field (.{key}) to read.')


	def __setattr__(self, key, value):
		if key in self.__dict__:
			raise AttributeError(f'Field (.{key}) already exists.')
		else:
			self.__dict__[key] = value


	def __getitem__(self, key):
		if key in self.__dict__:
			return self.__dict__[key]
		else:
			raise KeyError(f'No field ["{key}"] to read.')


	def __setitem__(self, key, value):
		if key in self.__dict__:
			raise KeyError(f'Field ["{key}"] already exists.')
		else:
			self.__dict__[key] = value
			return value


	def __iter__(self):
		for name, value in self.__dict__.items():
			yield (name, value)


	def __repr__(self):
		return f'Record({ ', '.join(f'{k}={v}' for k, v in self) })'


	def __contains__(self, key):
		return key in self.__dict__


	def __or__(self, other):

		match other:
			case dict() : key_values = other.items()
			case Obj()  : key_values = other
			case _:
				raise TypeError(f'Record cannot be combined with a {type(other)}: {other}.')

		for key, value in key_values:
			self.__setitem__(key, value)

		return self


def Table(header, *entries):

	table = []

	for entryi, entry in enumerate(entries):

		if entry is not None: # Allows for an entry to be easily omitted.

			if len(entry) != len(header):
				raise ValueError(f'Row {entryi + 1} has {len(entry)} entries but the header defines {len(header)} columns.')

			table += [Obj(**dict(zip(header, entry)))]

	return table

################################################################ Meta Primitives. ################################################################

class MetaError(Exception):

	def __init__(self, diagnostic = None, *, undefined_exported_symbol=None):
		self.diagnostic                = diagnostic
		self.undefined_exported_symbol = undefined_exported_symbol # When a meta-directive doesn't define a symbol it said it'd export.

	def __str__(self):
		return self.diagnostic


class Meta:

	def __init__(self):
		self.include_file_path = None


	def _start(self, include_file_path, include_directive_line_number):
		self.include_file_path             = include_file_path
		self.include_directive_line_number = include_directive_line_number
		self.__dict__['output']            = ''
		self.__dict__['indent']            = 0
		self.__dict__['within_macro']      = False
		self.__dict__['overloads']         = {}


	def __setattr__(self, key, value):

		if key not in ('include_file_path', 'include_directive_line_number') and self.__dict__['include_file_path'] is None:
			raise RuntimeError(f"The meta-directive needs to have an include-directive to use Meta.")

		self.__dict__[key] = value


	def _end(self):

		# No generated code if there's no #include directive.
		if self.include_file_path is None:
			return

		# We need to insert some stuff at the beginning of the file...
		generated   = self.output
		self.output = ''

		# Indicate origin of the meta-directive in the generated output.
		self.line(f'// [{self.include_file_path}:{self.include_directive_line_number}].')

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


	def line(self, input):

		strings = []

		match input:
			case types.GeneratorType() : strings = list(input)
			case list()                : strings = input
			case str()                 : strings = [input]
			case _                     : raise TypeError('Input type not supported.')

		for string in strings:
			for line in deindent(string).splitlines():
				self.output += (('\t' * self.indent) + line) + (' \\' if self.within_macro else '') + '\n'


	@contextlib.contextmanager
	def enter(self, header=None, opening=None, closing=None, *, indented=None):

		#
		# Automatically determine the scope parameters.
		#

		header_is = lambda *keywords: header is not None and re.search(fr'^\s*({'|'.join(keywords)})\b', header)

		if   header_is('#if', '#ifdef', '#elif', '#else') : suggestion = (None, '#endif'  , None)
		elif header_is('struct', 'union', 'enum')         : suggestion = ('{' , '};'      , None)
		elif header_is('case')                            : suggestion = ('{' , '} break;', None)
		elif header is not None and header.endswith('=')  : suggestion = ('{' , '};'      , True)
		else                                              : suggestion = ('{' , '}'       , None)

		if opening  is None: opening  = suggestion[0]
		if closing  is None: closing  = suggestion[1]
		if indented is None: indented = suggestion[2]

		#
		# If we're defining a macro, we have to escape the newlines if it happens to span across multiple lines.
		#

		if defining_macro := header_is('#define'):
			self.within_macro = True

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

				#
				# Determine the longest name.
				#

				just = 0

				for member in self.members:

					match member:
						case (name, value) : member_len = len(name)
						case  name         : member_len = len(name)

					just = max(just, member_len)

				#
				# Output each member.
				#

				for member in self.members:

					match member:
						case (name, value) : name, value = name, value
						case  name         : name, value = name, None

					# Implicit value.
					if value is None:
						self.meta.line(f'{self.enum_name}_{name},')

					# Explicit value.
					else:
						self.meta.line(f'{self.enum_name}_{name.ljust(just)} = {value},')

			# Provide the amount of members; it's its own enumeration so it won't have
			# to be explicitly handled in switch statements. Using a #define would also
			# work, but this could result in a name conflict; making the count be its own
			# enumeration prevents this collision since it's definition is scoped to where
			# it is defined.
			if self.count:
				self.meta.line(f'enum{enum_type} {{ {self.enum_name}_COUNT = {len(self.members)} }};')


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

			expansion = deindent(cstr(expansion))

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


	def ifs(self, items, *, style):

		def decorator(function):

			for item_index, item in enumerate(items):

				#
				# First iteration of the function should give us the condition of the if-statement.
				#

				iterator  = function(item)
				condition = next(iterator)

				#
				# Then generate the if-statement according to the desired style.
				#

				match style:

					case 'if':
						header  = f'if ({condition})'
						opening = None
						closing = None

					case '#if':
						header  = f'#if {condition}'
						opening = None
						closing = None

					case 'else if':
						header  = f'if ({condition})' if item_index == 0 else f'else if ({condition})'
						opening = None
						closing = None

					case _: raise ValueError('Unknown `if` style.')

				#
				# Next iteration of the function should generate the code within the if-statement.
				#

				with self.enter(header, opening, closing):

					stopped = False

					try:
						next(iterator)
					except StopIteration:
						stopped = True

					if not stopped:
						raise RuntimeError('Function of Meta.ifs did not return.')

		return decorator


def MetaDirective(
	index,
	source_file_path,
	header_line_number,
	include_file_path,
	include_directive_line_number,
	exports,
	imports,
	meta_globals,
	*,
	callback=None,
	meta_directives,
):
	def decorator(function):
		nonlocal meta_globals

		#
		# Start of callback.
		#

		if callback is None:
			callback_iterator = None
		else:
			callback_iterator = callback(
				index,
				source_file_path,
				header_line_number,
				include_file_path,
				include_directive_line_number,
				exports,
				imports,
				meta_directives,
			)
			next(callback_iterator)

		#
		# Determine the global namespace.
		#

		function_globals = {}

		for symbol in imports:

			# We have to skip modules since they're not deepcopy-able.
			if isinstance(meta_globals[symbol], types.ModuleType):
				function_globals[symbol] = meta_globals[symbol]

			# We deepcopy exported values so that if a meta-directive mutates it for some reason,
			# it'll only be contained within that meta-directive; this isn't really necessary,
			# but since meta-directives are evaluated mostly out-of-order, it helps keep the
			# uncertainty factor lower.
			else:
				function_globals[symbol] = copy.deepcopy(meta_globals[symbol])

		# Meta is special in that it is the only global singleton. This is for meta-directives that
		# define functions that use Meta itself to generate code, and that function might be called
		# in a different meta-directive. They all need to refer to the same object, so one singleton
		# must be made for everyone to refer to. Still, checks are put in place to make Meta illegal
		# to use in meta-directives that do not have an associated #include.
		function_globals['Meta'] = meta_globals['Meta']

		#
		# Execute the meta-directive.
		#

		function_globals['Meta']._start(include_file_path, include_directive_line_number)
		types.FunctionType(function.__code__, function_globals)()
		function_globals['Meta']._end()

		#
		# Copy the exported symbols into the collective namespace.
		#

		for symbol in exports:

			if symbol not in function_globals:
				raise MetaError(undefined_exported_symbol=symbol)

			meta_globals[symbol] = function_globals[symbol]

		#
		# End of callback.
		#

		if callback is not None:

			stopped = False

			try:
				next(callback_iterator)
			except StopIteration:
				stopped = True

			if not stopped:
				raise RuntimeError('Callback did not return.')

	return decorator

################################################################ Meta-Preprocessor. ################################################################

def do(*,
	output_dir_path,
	meta_py_file_path = None,
	source_file_paths,
	callback = None,
):

	#
	# Convert to pathlib.Path.
	#

	output_dir_path   =  pathlib.Path(output_dir_path )
	source_file_paths = [pathlib.Path(source_file_path) for source_file_path in source_file_paths]

	if meta_py_file_path is None:
		meta_py_file_path = pathlib.Path(output_dir_path, '__meta__.py')

	#
	# Get all of the #meta directives.
	#

	meta_directives = []

	def get_ports(string, diagnostic_header): # TODO Instead of diagnostic_header, we should pass in the file path and line number range.

		match string.split(':'):
			case [exports         ] : ports = [exports, None   ]
			case [exports, imports] : ports = [exports, imports]
			case _                  : raise MetaError(f'{diagnostic_header} Too many colons for meta-directive!')

		return [
			{
				symbol.strip()
				for symbol in port.split(',')
				if symbol.strip() # We'll be fine if there's extra commas; just remove the empty strings.
			} if port is not None else None for port in ports
		]

	for source_file_path in source_file_paths:

		remaining_lines       = open(source_file_path, 'rb').read().decode('UTF-8').splitlines()
		remaining_line_number = 1

		# Python file that might just be a big meta-directive.
		if source_file_path.suffix == '.py':

			while remaining_lines:

				#
				# See if there's an #include directive. # TODO Copy-pasted.
				#

				include_file_path = None
				include_line      = remaining_lines[0]
				tmp               = include_line
				tmp               = tmp.strip()

				if tmp.startswith('#include'):
					tmp = tmp.removeprefix('#include') # TODO Technically, there can be space after the #.
					tmp = tmp.strip()

					if tmp:
						end_quote = {
							'<' : '>',
							'"' : '"',
						}.get(tmp[0], None)

						if end_quote is not None and (length := tmp[1:].find(end_quote)) != -1:
							include_file_path      = pathlib.Path(output_dir_path, tmp[1:][:length])
							remaining_lines        = remaining_lines[1:]
							remaining_line_number += 1

				if include_file_path is None:
					include_line = None

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

				include_file_path = None
				include_line      = remaining_lines[0]
				tmp               = include_line
				tmp               = tmp.strip()

				if tmp.startswith('#include'):
					tmp = tmp.removeprefix('#include')
					tmp = tmp.strip()

					if tmp:
						end_quote = {
							'<' : '>',
							'"' : '"',
						}.get(tmp[0], None)

						if end_quote is not None and (length := tmp[1:].find(end_quote)) != -1:
							include_file_path      = pathlib.Path(output_dir_path, tmp[1:][:length])
							remaining_lines        = remaining_lines[1:]
							remaining_line_number += 1

				if include_file_path is None:
					include_line = None

				#
				# See if there's a block comment with #meta.
				#

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

				tmp                      = header_line
				tmp                      = tmp.strip()
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

						lines = deindent(lines)

						meta_directives += [types.SimpleNamespace(
							source_file_path   = source_file_path,
							header_line_number = header_line_number,
							include_file_path  = include_file_path,
							exports            = exports,
							imports            = imports,
							lines              = lines,
						)]

	#
	# Process the meta-directives' exports and imports.
	#

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
			meta_directive.imports = set(all_exports.keys())

	#
	# Sort the #meta directives.
	#

	# Meta-directives with empty imports are always done first,
	# because their exports will be implicitly imported to all the other meta-directives.
	remaining_meta_directives = [d for d in meta_directives if d.imports != set()]
	meta_directives           = [d for d in meta_directives if d.imports == set()]
	implicit_symbols          = { symbol for meta_directive in meta_directives for symbol in meta_directive.exports }
	current_symbols           = set(implicit_symbols)

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

	output_dir_path.mkdir(parents=True)

	meta_py = []

	# Additional context.
	meta_py += ['import MetaPreprocessor']
	meta_py += ['']

	for meta_directivei, meta_directive in enumerate(meta_directives):

		meta_directive_args  = []

		# Indicate where the nth #meta directive came from.
		meta_directive_args += [    meta_directivei                   ]
		meta_directive_args += [f"'{meta_directive.source_file_path}'"]
		meta_directive_args += [    meta_directive.header_line_number ]

		# If the #meta directive has a #include directive associated with it, provide the include file path and line number.
		meta_directive_args += [f"'{meta_directive.include_file_path}'"   if meta_directive.include_file_path is not None else None]
		meta_directive_args += [    meta_directive.header_line_number - 1 if meta_directive.include_file_path is not None else None]

		# Provide the name of the symbols that the Python snippet will define.
		meta_directive_args += [f'[{', '.join(f"'{symbol}'" for symbol in meta_directive.exports)}]']

		# The meta-directive explicitly has no imports.
		if meta_directive.imports == set():
			actual_imports = set()

		# The meta-directive lists its imports or have them be implicit given.
		else:
			actual_imports = (meta_directive.imports or set()) | implicit_symbols

		# Provide the name of the symbols that the Python snippet will be able to use.
		meta_directive_args += [f'[{', '.join(f"'{symbol}'" for symbol in actual_imports)}]']

		# Pass the dictionary containing all of the currently exported symbols so far.
		meta_directive_args += ['__META_GLOBALS__']

		# Provide other data common to all meta-directive handling.
		if callback:
			meta_directive_args += ['**__META_SHARED__']

		# All Python snippets are in the context of a function for scoping reasons.
		# The @MetaDirective will also automatically set up the necesary things to
		# execute the Python snippet and output the generated code.
		meta_py += [f"@MetaPreprocessor.MetaDirective({', '.join(map(str, meta_directive_args))})"]
		meta_py += [f'def __META__():']

		# List the things that the function is expected to define in the global namespace.
		if meta_directive.exports:
			meta_py += [f'\tglobal {', '.join(meta_directive.exports)}']

		# If the #meta directive has no code and doesn't export anything,
		# the function would end up empty, which is invalid Python syntax;
		# having a `pass` is a simple fix for this edge case.
		if not any(line.strip() for line in meta_directive.lines) and not meta_directive.exports:
			meta_py += ['\tpass']

		# Inject the #meta directive's Python snippet.
		meta_py += ['']
		meta_directive.meta_py_line_number = len(meta_py) + 1
		for line in meta_directive.lines:
			meta_py += [f'\t{line}' if line else '']
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

	except Exception as err: # TODO Better error messages.

		#
		# Determine the context of the issue.
		#

		diagnostic_tracebacks = []

		match err:

			case builtins.SyntaxError() | builtins.IndentationError():
				diagnostic_line_number = err.lineno
				raise err

			case _:

				# Get the traceback for the exception.
				diagnostic_tracebacks = traceback.extract_tb(sys.exc_info()[2])

				# We only care what happens after we begin executing the meta-directive's Python snippet.
				while diagnostic_tracebacks and diagnostic_tracebacks[0].name != '__META__':
					del diagnostic_tracebacks[0]

				# If there's none, then the issue happened outside of the meta-directive (e.g. MetaDirective).
				if not diagnostic_tracebacks:
					if isinstance(err, MetaError) and err.undefined_exported_symbol is not None:
						# MetaDirective caught a runtime bug.
						pass
					else:
						# There's some other sort of runtime exception; likely a bug with the MetaPreprocessor.
						raise err

				# Narrow down the details.
				diagnostic_tracebacks = [(tb.filename, tb.name, tb.lineno) for tb in diagnostic_tracebacks]

		#
		# Show lines of code for each layer of the traceback.
		#

		diagnostics = ''

		for origin, function_name, line_number in diagnostic_tracebacks:

			if origin == '<string>':

				diagnostic_directive = next((
					meta_directive
					for meta_directive in meta_directives
					if 0 <= line_number - meta_directive.meta_py_line_number <= len(meta_directive.lines)
				), None)

				assert diagnostic_directive is not None

				diagnostic_line_number = diagnostic_directive.header_line_number + 1 + (line_number - diagnostic_directive.meta_py_line_number)
				diagnostic_header      = f'# [{diagnostic_directive.source_file_path}:{diagnostic_line_number}]'

				diagnostic_lines   = diagnostic_directive.lines
				actual_line_number = line_number - diagnostic_directive.meta_py_line_number + 1

			else:
				diagnostic_header  = f'# [{pathlib.Path(origin).absolute().relative_to(pathlib.Path.cwd(), walk_up=True).parent}:{line_number}]'
				diagnostic_lines   = open(origin, 'r').read().splitlines()
				actual_line_number = line_number

			DIAGNOSTIC_WINDOW_SPAN = 2
			diagnostic_lines       = diagnostic_lines[max(actual_line_number - 1 - DIAGNOSTIC_WINDOW_SPAN, 0):]
			diagnostic_lines       = diagnostic_lines[:min(DIAGNOSTIC_WINDOW_SPAN * 2 + 1, len(diagnostic_lines))]

			diagnostics += '#' * 64 + '\n'
			diagnostics += '\n'.join(diagnostic_lines) + '\n'
			diagnostics += '#' * 64 + '\n'
			diagnostics += f'{diagnostic_header} {function_name if function_name != '__META__' else 'Meta-directive root'}.\n\n'

		#
		# Determine the reason for the exception.
		#

		match err:

			case builtins.SyntaxError():
				diagnostic_message = f'Syntax error: {err.text.strip()}'

			case builtins.NameError() | builtins.KeyError() | builtins.ValueError():
				diagnostic_message = f'Error: {str(err).removesuffix('.')}.'

			case builtins.AssertionError():
				diagnostic_message = err.args[0] if err.args else f'Assertion failed!'

			case MetaError():
				if err.undefined_exported_symbol is not None:
					diagnostic_message = f'Meta-directive did not define "{err.undefined_exported_symbol}"!'
				else:
					diagnostic_message = f'{str(err).removesuffix('.')}.'

			case _:
				diagnostic_message = f'({type(err)}) {str(err).removesuffix('.')}.'

		#
		# Report the exception.
		#

		diagnostics = diagnostics.rstrip() + '\n'
		diagnostics += f'# {diagnostic_message}'
		raise MetaError(diagnostics) from err
