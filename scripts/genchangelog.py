#!/usr/bin/env python3
import sys
import datetime
import re

CHANGELOG_FORMAT = """
{version} ({date})
----------------------

{description}
"""
TIXURL = "https://github.com/hsoft/moneyguru/issues/{}"

def tixgen(tixurl):
    """This is a filter *generator*. tixurl is a url pattern for the tix with a {0} placeholder
    for the tix #
    """
    urlpattern = tixurl.format('\\1') # will be replaced buy the content of the first group in re
    R = re.compile(r'#(\d+)')
    repl = '`#\\1 <{}>`__'.format(urlpattern)
    return lambda text: R.sub(repl, text)


re_changelog_header = re.compile(r'=== ([\d.b]*) \(([\d\-]*)\)')
def read_changelog_file(filename):
    def iter_by_three(it):
        while True:
            version = next(it)
            date = next(it)
            description = next(it)
            yield version, date, description

    with open(filename, 'rt', encoding='utf-8') as fp:
        contents = fp.read()
    splitted = re_changelog_header.split(contents)[1:] # the first item is empty
    # splitted = [version1, date1, desc1, version2, date2, ...]
    result = []
    for version, date_str, description in iter_by_three(iter(splitted)):
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        d = {'date': date, 'date_str': date_str, 'version': version, 'description': description.strip()}
        result.append(d)
    return result


def changelog_to_rst(changelogpath):
    changelog = read_changelog_file(changelogpath)
    tix = tixgen(TIXURL)
    for log in changelog:
        description = tix(log['description'])
        # The format of the changelog descriptions is in markdown, but since we only use bulled list
        # and links, it's not worth depending on the markdown package. A simple regexp suffice.
        description = re.sub(r'\[(.*?)\]\((.*?)\)', '`\\1 <\\2>`__', description)
        rendered = CHANGELOG_FORMAT.format(version=log['version'], date=log['date_str'],
            description=description)
        print(rendered)

if __name__ == '__main__':
    changelog_to_rst(sys.argv[1])
