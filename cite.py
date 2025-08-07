import re, sys, types, pathlib, string, collections, difflib
from ..pxd.ui    import UI
from ..pxd.log   import log, did_you_mean
from ..pxd.utils import *

CITATION_TAG = '@' '/' # Written like this so that the script won't accidentally think this is a citation.
ui           = UI('cite', 'Manage citations within the codebase.')



################################################################################################################################



def __get_file_paths():

    #
    # TODO We have dumb logic here to get something that sort of
    # resembles .gitignore. It's not very good, because apparently
    # there's no easy way to do recursive `**` globs that's built-in. Sigh.
    #

    citeignore_file_path = root(f'./.citeignore')

    if citeignore_file_path.is_file():

        citeignore_entries = [
            line.strip()
            for line in citeignore_file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]

    else:
        citeignore_entries = []

    def is_ignored(file_path):

        for pattern in citeignore_entries:
            if pattern.startswith('*.'):
                if file_path.match(pattern):
                    return True
            elif pattern.endswith('/'):
                if any(part == pattern.removesuffix('/') for part in file_path.parts):
                    return True
            else:
                assert False, f'Unsupported pattern: {pattern}'

        return False

    return [
        pathlib.Path(parent_file_path, file_name)
        for parent_file_path, dirs, file_names in root('./').walk()
        for file_name in file_names
        if not pathlib.Path(parent_file_path, file_name).is_dir() and not is_ignored(pathlib.Path(parent_file_path, file_name))
    ]



################################################################################################################################



def __get_citations():

    citations = []
    issues    = []

    for file_path in __get_file_paths():



        # Show the current file we're processing.

        log(f'\x1B[2K\r{file_path}', end = '', ansi = 'fg_green');



        # Some stuff might be binary, so we'll skip over it when we can't read it properly.

        try:
            lines = file_path.read_text().splitlines()
        except UnicodeDecodeError:
            continue



        # Look for the magic citation tags and try the parse the citations.

        class ParsingIssue(Exception):
            pass

        for line_number, line, column in (
            (line_i + 1, line, match.start())
            for line_i, line in enumerate(lines)
            for match in re.finditer(CITATION_TAG, line)
        ):

            def report_issue(reason):
                nonlocal issues
                issues += [types.SimpleNamespace(
                    file_path   = file_path,
                    line_number = line_number,
                    reason      = reason,
                )]

            try:

                remainder = line[column + len(CITATION_TAG):]
                citation  = types.SimpleNamespace(
                    file_path   = file_path,
                    line_number = line_number,
                    column      = column,
                    line        = line,
                )



                # Get every citation field until we reach the source.
                # e.g:
                # >
                # >    (AT)/pg 123/sec abc/`The Bible`.
                # >         ^^^^^^ ^^^^^^^ ^
                # >

                citation.fields = {}

                while True:



                    # See if we've found the source.

                    for citation.source_usage in (None, 'by', 'url'):



                        # Determine how the source name will be used.
                        # Some sources are "inlined", that is, they don't have a source definition, like for instance URLs.
                        # Most citations, however, reference a source that'll be defined elsewhere.
                        # e.g:
                        # >
                        # >    (AT)/pg 123/sec abc/`The Bible`.
                        # >                        ^ Not inlined; defined else where.
                        # >
                        # >    (AT)/pg 123/sec abc/by:`Phuc Doan`.
                        # >                        ^ Inlined; no source definition for `Phuc Doan` needed.
                        # >
                        # >    (AT)/pg 123/sec abc/url:`www.google.com`.
                        # >                        ^ Inlined; no source definition for `www.google.com` needed.
                        # >

                        if citation.source_usage is None:
                            prefix = '`'
                        else:
                            prefix = f'{citation.source_usage}:`'

                        if not remainder.startswith(prefix):
                            continue

                        remainder = remainder.removeprefix(prefix)



                        # Get the source name.
                        # e.g:
                        # >
                        # >    (AT)/pg 123/sec abc/url:`www.google.com`.
                        # >                             ^~~~~~~~~~~~~^
                        # >

                        start                            = len(line) - len(remainder)
                        citation.source_name, *remainder = remainder.split('`', 1)
                        end                              = start + len(citation.source_name)

                        if remainder == []:
                            raise ParsingIssue(f'Missing closing backtick (`) after source name.')

                        remainder, = remainder

                        citation.source_name         = citation.source_name.strip()
                        citation.source_name_columns = (start, end)

                        if not citation.source_name:
                            report_issue('Empty source name.')

                        break

                    else:
                        citation.source_usage = ... # Haven't found the source yet.

                    if citation.source_usage is not ...:
                        break



                    # Find the end of the field.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >         ~~~~~~^
                    # >

                    field, *remainder = remainder.split('/', 1)

                    field = field.strip()

                    if not field:
                        raise ParsingIssue(f'Expected a field name.')

                    if remainder == []:
                        raise ParsingIssue(f'Expected a forward-slash (/).')

                    remainder, = remainder



                    # Get the field name and content.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >         ^^ ^^^
                    # >

                    field_name, *field_content = field.split(' ', 1)

                    if field_content == []:
                        raise ParsingIssue(f'Field "{field_name}" given no value.')

                    field_content, = field_content

                    if field_name in citation.fields:
                        raise ParsingIssue(f'Field "{field_name}" specified more than once.')

                    citation.fields[field_name] = field_content



                # We have now scanned through the entire citation.
                # e.g:
                # >
                # >    (AT)/by Phuc Doan/pg 13/sec abc/`The Bible`.
                # >    ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
                # >

                citation.text = line[column : len(line) - len(remainder)]



                # Validate each field.

                citation.listing = None

                for field_name, field_content in citation.fields.items():

                    match field_name:



                        # Get the page number.
                        # e.g:
                        # >
                        # >    (AT)/by Phuc Doan/pg 13/sec abc/`The Bible`.
                        # >                         ^^
                        # >

                        case 'pg':

                            if any(c in field_content for c in string.whitespace):
                                report_issue(
                                    f'Field "{field_name}" is "{field_content}" which has whitespace; '
                                    f'probably a mistake?'
                                )

                            elif not all(character in string.digits for character in field_content):
                                report_issue(
                                    f'Field "{field_name}" is "{field_content}" which has characters other than digits 0-9; '
                                    f'probably a mistake?'
                                )

                            elif field_content.startswith('0'):
                                report_issue(
                                    f'Field "{field_name}" is "{field_content}" which starts with digit 0; '
                                    f'probably a mistake?'
                                )



                        # Get the listing.
                        # e.g:
                        # >
                        # >    (AT)/by Phuc Doan/pg 13/sec abc/`The Bible`.
                        # >                                ^^^
                        # >

                        case 'tbl' | 'fig' | 'sec':

                            if citation.listing is not None:
                                report_issue(
                                    f'Fields "{citation.listing}" and "{field_name}" both given; '
                                    f'only at most one listing field is needed.'
                                )

                            else:

                                citation.listing = field_name

                                if not field_content.startswith(tuple(string.ascii_letters + string.digits)):
                                    report_issue(
                                        f'Field "{field_name}" is "{field_content}" which does not start with an alphanumeric character; '
                                        f'probably a mistake?'
                                    )

                                elif not field_content.endswith(tuple(string.ascii_letters + string.digits)):
                                    report_issue(
                                        f'The "{field_name}" field value is "{field_content}" which does not end with an alphanumeric character; '
                                        f'probably a mistake?'
                                    )

                                elif any(c in field_content for c in string.whitespace):
                                    report_issue(
                                        f'Field "{field_name}" is "{field_content}" which has whitespace; '
                                        f'probably a mistake?'
                                    )

                                elif not all(c in string.ascii_letters + string.digits + '.-' for c in field_content):
                                    report_issue(
                                        f'Field "{field_name}" is "{field_content}" which has a character typically not associated with listing codes; '
                                        f'probably a mistake?'
                                    )



                        # Unknown field.

                        case _:
                            report_issue(f'Field "{field_name}" is not supported.')



                # If a colon is next, then the citation is actually a source definition;
                # otherwise, it should be a reference to a source.
                # e.g:
                # >
                # >    The user guide states that we need to do X, Y, and Z. (AT)/`RSX`.
                # >                                                          ^^^^^^^^^^ Citation that's a reference.
                # >
                # >    (AT)/`RSX`: RockSat-X User Guide (August 31, 2023) (Rev-Draft).
                # >              ^ Citation that's a source definition.
                # >

                if remainder.strip().startswith(':'):

                    if citation.source_usage is not None:
                        raise ParsingIssue(f'Citation cannot have a "{citation.source_usage}" source and also be a source definition.')

                    citation.source_usage = 'definition'

                    if citation.fields:
                        report_issue(f'A source definition should not have fields.')

                elif citation.source_usage is None:
                    citation.source_usage = 'reference'



                citations += [citation]



            # Some sort of irrecoverable issue was encountered while parsing the citation...

            except ParsingIssue as error:
                report_issue(error.args[0])



    # Organize the citations by source names and then the usage of the source.
    # This is how we determine if the sources are being used properly.
    # We also sort it so the output will be nice.

    sources = collections.defaultdict(lambda: collections.defaultdict(lambda: []))

    def sorting(citation):

        try:
            pg = int(citation.fields.get('pg', 0))
        except ValueError:
            pg = 0 # The page number field is actually malformed, but we'll silently treat it as a zero.

        return (
            citation.source_name.lower(),
            citation.source_usage == 'reference',
            pg,
            citation.listing or '',
            citation.fields.get(citation.listing, ''),
            citation.file_path,
            citation.line_number
        )

    for citation in sorted(citations, key = sorting):
        sources[citation.source_name][citation.source_usage] += [citation]

    citations = [
        citation
        for source_usage_citations in sources.values()
        for source_citations in source_usage_citations.values()
        for citation in source_citations
    ]



    # Find additional issues.

    for source_name, source_usage_citations in sources.items():

        match source_usage_citations:


            # A source with a single definition and some citations that reference it.

            case { 'definition': [definition], 'reference': [first, *others], **rest } if not rest:
                pass # This is okay.



            # Citations that are URLs.

            case { 'url': urls, **rest } if not rest:
                pass # This is okay.



            # Citations that are authorized.

            case { 'by': bys, **rest } if not rest:
                pass # This is okay.



            # Citation references a source that's not defined anywhere.

            case { 'reference' : references, **rest } if not rest:

                for reference_i, reference in enumerate(references):

                    issues += [types.SimpleNamespace(
                        file_path   = reference.file_path,
                        line_number = reference.line_number,
                        reason      = f'Undefined reference to source "{reference.source_name}".',
                    )]



            # A source that's defined multiple times.

            case { 'definition' : [first, *others] } if others:

                for other in others:
                    issues += [types.SimpleNamespace(
                        file_path   = other.file_path,
                        line_number = other.line_number,
                        reason      = f'Source "{other.source_name}" is already defined at [{first.file_path}:{first.line_number}]',
                    )]



            # A source that's not referenced by any citation.

            case { 'definition' : [definition], **rest } if not rest:

                issues += [types.SimpleNamespace(
                    file_path   = definition.file_path,
                    line_number = definition.line_number,
                    reason      = f'Source "{definition.source_name}" never used',
                )]



            # A source with conflicting usages.
            # e.g:
            # >
            # >    (AT)/by:`google.com`.  <- Is "google.com" an author, a URL, or a source that's defined elsewhere?
            # >    (AT)/url:`google.com`. <- "
            # >    (AT)/`google.com`.     <- "
            # >

            case _ if len(source_usage_citations) >= 2:

                for source_usage, source_citations in source_usage_citations.items():
                    for citation in source_citations:
                        issues += [types.SimpleNamespace(
                            file_path   = citation.file_path,
                            line_number = citation.line_number,
                            reason      = f'Source "{source_name}" in this citation has the usage of "{source_usage}", which is conflicting with other citations.',
                        )]



            # Unhandled case.

            case _:
                issues += [types.SimpleNamespace(
                    file_path   = citation.file_path,
                    line_number = citation.line_number,
                    reason      = f'Source "{source_name}" with unhandled set of usages: {list(source_usage_citations.keys())}.',
                )]



    # Clear the line where we were showing the current file we were processing.

    log(f'\x1B[2K\r', end = '');

    return citations, issues



################################################################################################################################



def __log_citations(citations, issues):

    if citations:

        for citation, ljust in zip(citations, ljusts((citation.file_path, citation.line_number) for citation in citations)):

            log('| {0} : {1} | '.format(*ljust), end = '')


            match citation.source_usage:
                case 'definition': source_color = 'bg_blue'
                case 'reference' : source_color = 'fg_cyan'
                case _           : source_color = 'fg_magenta'

            log(citation.line[                                : citation.source_name_columns[0]].lstrip(), end = '', ansi = 'fg_bright_black')
            log(citation.line[citation.source_name_columns[0] : citation.source_name_columns[1]]         , end = '', ansi = (source_color, 'bold'))
            log(citation.line[citation.source_name_columns[1] :                                ].rstrip(), end = '', ansi = 'fg_bright_black')
            log()

    else:

        log('No citations found.')

    if issues:

        with log(ansi = 'fg_yellow'):

            log()

            for issue, ljust in zip(issues, ljusts((issue.file_path, issue.line_number) for issue in issues)):
                log('[WARNING] {0} : {1} | {2}'.format(*ljust, issue.reason))



################################################################################################################################



@ui('Validate and list every citation.')
def find(
    specific_source_name : ( str         , 'Source name to filter by; otherwise, list everything.'      ) = None,
    rename               : ((str, 'flag'), 'If given, replaces the sources of citations with a new one.') = None,
):



    # Some basic checks on parameters.

    if rename is not None:

        rename = rename.strip()

        if specific_source_name is None:
            log(f'[ERROR] In order rename citation sources, the old source name must be also given.', ansi = 'fg_red')
            return 1

        if '`' in rename:
            log(f'[ERROR] The new source name "{rename}" cannot have a backtick (`).', ansi = 'fg_red')
            return 1

        if rename == '':
            log(f'[ERROR] The source cannot be renamed to an empty string.', ansi = 'fg_red')
            return 1

        if rename == specific_source_name:
            log(f'The new source name "{rename}" is the same as the old one; no renaming will be done.')
            return 0

    all_citations, issues = __get_citations()



    # If the user only wants to look for citations of a specific source name,
    # then filter down the list of citations.

    if specific_source_name is not None:

        filtered_citations = [
            citation
            for citation in all_citations
            if citation.source_name == specific_source_name
        ]



        # If we end up filtering everything out,
        # then show all of the citations and tell the user there's no citation by that source name.

        if not filtered_citations:

            __log_citations(all_citations, issues)
            log()
            did_you_mean(
                f'No citations associated with "{specific_source_name}" was found.',
                specific_source_name,
                OrdSet(citation.source_name for citation in all_citations),
            )

            return 0 # I'm arbitrarily saying no error here.



    # No filtering done.

    else:

        filtered_citations = all_citations



    # Show the citations and issues if any.

    __log_citations(filtered_citations, issues)



    # Move onto the process of renaming, if requested.

    if rename is None:
        return

    if any(citation.source_name == rename for citation in all_citations):
        log(f'[WARNING] The new source name "{rename}" is the name of an already existing source.', ansi = 'fg_yellow')

    log()
    log(f'Enter "yes" to replace the source names with "{rename}"; otherwise abort: ', end ='')

    try:
        response = input()
    except KeyboardInterrupt:
        log()
        response = None

    if response != 'yes':
        log(f'Aborted the renaming.')
        return 1



    # Actually perform the renaming operation now.

    for file_path, file_citations in coalesce((citation.file_path, citation) for citation in filtered_citations).items():

        file_lines = file_path.read_text().splitlines(keepends = True)



        # Iterate through the citations on the line backwards so we can replace the source names properly.

        for citation in sorted(file_citations, key = lambda citation: (citation.line_number, -citation.source_name_columns[0])):

            file_lines[citation.line_number - 1] = (
                file_lines[citation.line_number - 1][:citation.source_name_columns[0]] +
                rename +
                file_lines[citation.line_number - 1][citation.source_name_columns[1]:]
            )



        # Rejoin the file lines while preserving line-endings.

        file_path.write_text(''.join(file_lines))



    log(f'Renamed {len(filtered_citations)} citations.')



    # Typically renames are useful for fixing citation issues,
    # so we show the remaining issues that there may be.

    new_citations, issues = __get_citations()

    new_citations = [
        citation
        for citation in new_citations
        if citation.source_name == rename
    ]

    log()
    __log_citations(new_citations, issues)
