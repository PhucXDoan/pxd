#!/usr/bin/env python3
import pathlib, types, contextlib, re, traceback, builtins, sys, enum, copy

################################################################ Helpers ################################################################

def Str(x):
	match x:
		case bool  () : return str(x).lower()
		case float () : return str(int(x) if x.is_integer() else x)
		case _        : return str(x)

class Obj: # TODO Improve.

	def __init__(self, dct=None, **fields):
		assert dct is None or not fields, \
			'Obj has both an argument and kwargs; likely a mistake?'
		for key, value in (fields if dct is None else dct).items():
			self.__dict__[key] = value

	def __getattr__(self, key):
		assert key in ('__deepcopy__', '__setstate__'), \
			f'The Obj has no field (.{key}) to read.'
		raise AttributeError

	def __setattr__(self, key, value):
		assert key in self.__dict__, \
			f'The Obj has no field (.{key}) to write.'
		self.__dict__[key] = value

	def __getitem__(self, key):
		assert key in self.__dict__, \
			f'The Obj has no field [`{key}`] to read.'
		return self.__dict__[key]

	def __setitem__(self, key, value):
		assert key in self.__dict__, \
			f'The Obj has no field [`{key}`] to write.'
		self.__dict__[key] = value
		return value

	def __iter__(self):
		for name, value in self.__dict__.items():
			yield (name, value)

	def __repr__(self):
		return f'Obj({ ', '.join(f'{k} = {v}' for k, v in self) })'

	def __contains__(self, key):
		return key in self.__dict__

class AddOn:

	def __init__(self, dct=None, **fields):
		assert dct is None or not fields, \
			'AddOn has both an argument and kwargs; likely a mistake?'
		for key, value in (fields if dct is None else dct).items():
			self.__dict__[key] = value

	def __getattr__(self, key):
		assert key in ('__deepcopy__', '__setstate__'), \
			f'The AddOn has no field (.{key}) to read.'
		raise AttributeError

	def __setattr__(self, key, value):
		assert key not in self.__dict__, \
			f'The AddOn has field (.{key}) already.'
		self.__dict__[key] = value

	def __getitem__(self, key):
		assert key in self.__dict__, \
			f'The AddOn has no field [`{key}`] to read.'
		return self.__dict__[key]

	def __setitem__(self, key, value):
		assert key not in self.__dict__, \
			f'The  has field [`{key}`] already.'
		self.__dict__[key] = value
		return value

	def __iter__(self):
		for name, value in self.__dict__.items():
			yield (name, value)

	def __repr__(self):
		return f'AddOn({ ', '.join(f'{k} = {v}' for k, v in self) })'

	def __contains__(self, key):
		return key in self.__dict__

	def __or__(self, other):
		match other:
			case dict():
				for key, value in other.items():
					self.__setitem__(key, value)
				return self
			case Obj():
				for key, value in other:
					self.__setitem__(key, value)
				return self
			case _:
				assert False, f'This operation is not supported on this type.'

def Table(header, *entries): # TODO Improve.

	table = []

	for entry in entries:
		if entry is not None: # Allows for an entry to be easily omitted.
			table += [Obj(**dict(zip(header, entry)))]

	return table

################################################################ Meta Primitives ################################################################

class MetaError(Exception):

	def __init__(self, diagnostic = None, *, undefined_exported_symbol=None):
		self.diagnostic                = diagnostic
		self.undefined_exported_symbol = undefined_exported_symbol

	def __str__(self):
		return self.diagnostic

class Meta:

	def __init__(self):
		self.include_file_path = None

	def _start(self, include_file_path, include_directive_line_number):
		self.include_file_path             = include_file_path
		self.include_directive_line_number = include_directive_line_number
		self.output                        = ''
		self.indent                        = 0
		self.within_macro                  = False
		self.overloads                     = {}

	def _end(self):
		if self.include_file_path is not None:

			generated   = self.output
			self.output = ''

			self.line(f'// [{self.include_file_path}:{self.include_directive_line_number}].')

			# Put any overloaded macros first.
			if self.overloads:
				if self.output:
					self.line()
				for macro_name, (arg_names, determiner_names, nondeterminer_names) in self.overloads.items():
					self.define(f'{macro_name}({', '.join(arg_names)})', f'_{macro_name}__##{'##'.join(determiner_names)}({', '.join(nondeterminer_names)})')

			# Insert rest of the code that was generated.
			if generated:
				if self.output:
					self.line()
				self.line(generated)

			pathlib.Path(self.include_file_path).parent.mkdir(parents=True, exist_ok=True)
			open(self.include_file_path, 'w').write(self.output)

	def line(self, input='\n\n'): # Outputs a single empty line by default.
		assert self.include_file_path is not None

		strings = []

		match input:
			case types.GeneratorType() : strings = list(input)
			case list()                : strings = input
			case str()                 : strings = [input]
			case _                     : raise TypeError('Input type not supported.')

		for string in strings:

			# Split to process each line in order to do indenting correctly for multilined input strings.
			lines = (string + '\n').splitlines()

			# Remove first empty line; useful for multilined strings.
			if lines and lines[0].strip() == '':
				lines = lines[1:]

			# Remove last empty line; useful for multilined strings.
			if lines and lines[-1].strip() == '':
				lines = lines[:-1]

			global_indent = None
			for line in lines:

				# Determine line's indent level.
				line_indent = len(line) - len(line.lstrip('\t'))

				# Determine the whole string's indent level based on the first line with actual text.
				if global_indent is None and line.strip():
					global_indent = line_indent

				# Set indents appropriately.
				line         = line.removeprefix('\t' * min(line_indent, global_indent or 0))
				line         = '\t' * self.indent + line if line.strip() else ''
				self.output += line + (' \\' if self.within_macro else '') + '\n'

	@contextlib.contextmanager
	def enter(self, header=None, opening=None, closing=None, *, indented=None):
		assert self.include_file_path is not None

		#
		# Automatically determine the scope parameters.
		#

		defining_macro = False

		def header_is(*keywords):
			string = fr'^\s*({'|'.join(keywords)})\b'
			return header is not None and re.search(string, header)

		if header_is('#if', '#ifdef', '#elif', '#else'):
			if closing is None: closing = '#endif'

		elif header_is('struct', 'union', 'enum'):
			if opening is None: opening = '{'
			if closing is None: closing = '};'

		elif header_is('case'):
			if opening is None: opening  = '{'
			if closing is None: closing  = '} break;'

		elif header_is('#define'):
			defining_macro    = True
			self.within_macro = True

		elif header is not None and header.endswith('='):
			if opening  is None: opening  = '{'
			if closing  is None: closing  = '};'
			if indented is None: indented = True;

		else:
			if opening is None: opening = '{'
			if closing is None: closing = '}'

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

	def enums(self, *args):
		assert self.include_file_path is not None
		return self.__enums(self, *args)

	class __enums:

		def __init__(self, meta, enum_name, underlying_type, members = None, count = True):

			self.meta            = meta
			self.enum_name       = enum_name
			self.underlying_type = underlying_type
			self.members         = members
			self.count           = count

			if members is not None: # The list of members are already provided?
				self.__exit__()

		def __enter__(self): # The user provides the list of members in a `with` context.

			if self.members is not None:
				# TODO Better error message.
				raise ValueError('Argument `members` cannot be provided if a `with` context is used.')

			self.members = []
			return self.members

		def __exit__(self, *dont_care_about_exceptions):

			enum_type = '' if self.underlying_type is None else f' : {self.underlying_type}'

			with self.meta.enter(f'enum {self.enum_name}{enum_type}'):

				# Determine the longest name.
				member_name_just = 0
				for member in self.members:
					match member:
						case (name, value) : member_name_just = max(member_name_just, len(name))
						case  name         : member_name_just = max(member_name_just, len(name))

				# Output each member.
				for member in self.members:

					match member:
						case (name, value) : member_name, member_value = name, value
						case  name         : member_name, member_value = name, None

					# Implicit value.
					if member_value is None:
						self.meta.line(f'{self.enum_name}_{member_name},')

					# Explicit value.
					else:
						self.meta.line(f'{self.enum_name}_{member_name.ljust(member_name_just)} = {member_value},')

			# Provide the amount of members; it's its own enumeration so it won't have
			# to be explicitly handled in switch statements. Using a #define would also
			# work, but this could result in a name conflict. Making the count be its own
			# enumeration prevents this collision since it's scoped.
			if self.count:
				self.meta.line(f'enum{enum_type} {{ {self.enum_name}_COUNT = {len(self.members)} }};')

	def define(self, *lhs_rhs_pairs, do_while=False):

		lhs, rhs = lhs_rhs_pairs

		if isinstance(rhs, str) and '\n' in rhs:
			with self.enter(f'#define {lhs}'):
				if do_while:
					with self.enter('do', '{', '}\nwhile (false)'):
						self.line(rhs)
				else:
					self.line(rhs)
		else:
			expansion = Str(rhs).strip()

			if do_while:
				self.line(f'#define {lhs} do {{ {expansion} }} while (false)')
			else:
				self.line(f'#define {lhs} {expansion}')

	def overload(self, macro_name, args, expansion):

		arg_names                           = [arg[0] if isinstance(arg, tuple) else arg for arg in args]
		determiner_names, determiner_values = zip(*[ arg for arg in args if     isinstance(arg, tuple)])
		nondeterminer_names                 =      [ arg for arg in args if not isinstance(arg, tuple)]
		overload                            = (arg_names, determiner_names, nondeterminer_names)

		if macro_name in self.overloads:
			assert self.overloads[macro_name] == overload
		else:
			self.overloads[macro_name] = overload

		self.define(f'_{macro_name}__{'__'.join(map(Str, determiner_values))}({', '.join(nondeterminer_names)})', expansion)

	def ifs(self, xs, *, style):

		def decorator(function):

			for xi, x in enumerate(xs):

				iterator  = function(x)
				condition = next(iterator)

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
						header  = f'if ({condition})' if xi == 0 else f'else if ({condition})'
						opening = None
						closing = None

					case _: raise ValueError('Unknown `if` style.') # TODO Multiple periods...

				with self.enter(header, opening, closing):
					try:
						next(iterator)
					except StopIteration:
						pass

		return decorator

def MetaDirective(include_file_path, include_directive_line_number, exports, imports, meta_globals):
	def decorator(function):
		nonlocal meta_globals

		#
		# Execute the meta-directive.
		#

		function_globals = {
			symbol : meta_globals[symbol] if isinstance(meta_globals[symbol], types.ModuleType) else copy.deepcopy(meta_globals[symbol])
			for symbol in imports
		}

		function_globals['Meta'] = meta_globals['Meta']

		function_globals['Meta']._start(include_file_path, include_directive_line_number)
		types.FunctionType(function.__code__, function_globals)()
		function_globals['Meta']._end()

		#
		# Ensure the meta-directive actually defined all of the symbols it said it'd export.
		#

		for symbol in exports:

			if symbol not in function_globals:
				raise MetaError(undefined_exported_symbol=symbol)

			meta_globals[symbol] =  function_globals[symbol]

	return decorator

################################################################ Meta-Preprocessor ################################################################

def do(*,
	output_dir_path,
	meta_py_file_path = None,
	source_file_paths,
):

	output_dir_path   =  pathlib.Path(output_dir_path )
	source_file_paths = [pathlib.Path(source_file_path) for source_file_path in source_file_paths]

	if meta_py_file_path is None:
		meta_py_file_path = pathlib.Path(output_dir_path, '__meta__.py')

	#
	# Get all of the #meta directives.
	#

	meta_directives = []

	def get_ports(string, diagnostic_header):

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
						include_file_path  = None,
						exports            = exports,
						imports            = imports,
						lines              = remaining_lines,
						diagnostic_header  = diagnostic_header, # TODO Needed?
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

						lines         = []
						global_indent = None
						ending        = -1

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

							# Determine indent level.
							original_line_indent = len(line) - len(line.lstrip('\t'))

							# Determine global indent.
							is_comment = line.strip().startswith('#')
							nonempty   = line.strip() != ''
							if global_indent is None and nonempty and not is_comment:
								global_indent = original_line_indent

							# Cut away the extraneous indent. It's possible that the line has less
							# indentation than the global indentation, but we won't worry too much about that, honestly.
							line = line.removeprefix('\t' * min(original_line_indent, global_indent or 0))

							# Got line!
							line   = line.rstrip()
							lines += [line]

						meta_directives += [types.SimpleNamespace(
							source_file_path   = source_file_path,
							header_line_number = header_line_number,
							include_file_path  = include_file_path,
							exports            = exports,
							imports            = imports,
							lines              = lines,
							diagnostic_header  = diagnostic_header, # TODO Needed?
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
	meta_py += ["__META_GLOBALS__ = { 'Meta' : MetaPreprocessor.Meta() }"]
	meta_py += ['']

	for meta_directive in meta_directives:

		meta_directive_args  = []

		# Indicate where the #meta directive came from.
		meta_py += [f'# {meta_directive.source_file_path}:{meta_directive.header_line_number}.']

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
		exec(meta_py, {}, {})

	except Exception as err:

		#
		# Determine the line numbers within the original source file containing the meta-directives.
		#

		diagnostic_tracebacks = []

		match err:

			case builtins.SyntaxError() | builtins.IndentationError():
				diagnostic_line_number = err.lineno
				assert False # TODO.

			case _:

				# Get the traceback for the exception.
				diagnostic_tracebacks = traceback.extract_tb(sys.exc_info()[2])

				# We only care what happens after we begin executing the meta-directive's Python snippet.
				while diagnostic_tracebacks and diagnostic_tracebacks[0].name != '__META__':
					del diagnostic_tracebacks[0]

				# Narrow down the details.
				diagnostic_tracebacks = [(tb.filename, tb.name, tb.lineno) for tb in diagnostic_tracebacks]

		if not diagnostic_tracebacks:
			raise err

		#
		#
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

			case builtins.NameError():
				diagnostic_message = f'Name error: {err}.' # TODO Better error message.

			case builtins.KeyError():
				diagnostic_message = f'Key error: {err}.' # TODO Better error message.

			case builtins.AssertionError():
				diagnostic_message = err.args[0] if err.args else f'Assertion failed!'

			case MetaError():
				if err.undefined_exported_symbol is not None:
					diagnostic_message = f'Meta-directive did not define "{err.undefined_exported_symbol}"!' # TODO Better error message.
				else:
					diagnostic_message = f'{err}.' # TODO Better error message.

			case _:
				diagnostic_message = f'({type(err)}) {err}.'

		#
		# Report the exception.
		#

		diagnostics = diagnostics.rstrip() + '\n'
		diagnostics += f'# {diagnostic_message}'

		raise MetaError(diagnostics) from err
