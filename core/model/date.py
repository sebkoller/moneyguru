# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import re
from calendar import monthrange
from datetime import date, datetime, timedelta

from core.model._ccore import inc_date
from core.trans import tr
from core.util import iterdaterange

ONE_DAY = timedelta(1)

# --- Date Ranges

class DateRange:
    """A range between two dates.

    Much of the information supplied by moneyGuru is done so in a date range context. Give me a
    profit report for this year, give me a running total chart for this month, and so on and so on.

    This class represents that range, supplies a couple of useful methods, and can be subclassed to
    represent more specific ranges, such as :class:`YearRange`.

    Some ranges are :attr:`navigable <can_navigate>`, which means that they mostly represent a
    duration, which can be placed anywhere in time. We can thus "navigate" time with this range
    using prev/next buttons. Example: :class:`MonthRange`.

    Other ranges, such as :class:`YearToDateRange`, represent two very fixed points in time: 1st of
    january to today. These are not navigable.

    The two most important attributes of a date range: :attr:`start` and :attr:`end`.

    A couple of operators that can be used with ranges:

    * r1 == r2 -> only if start and end are the same.
    * bool(r) == True -> if it's a range that makes sense (start <= end)
    * r1 & r2 -> intersection range between the two.
    * date in r -> if start <= date <= end
    * iter(r) -> iterates over all dates between start and end (inclusive).

    The thing is hashable while, at the same time, being mutable. Use your common sense: don't go
    around using date ranges as dict keys and then mutate them. Also, mutation of a date range is
    a rather rare occurence and is only needed in a couple of tight spots. Try avoiding them.
    """
    def __init__(self, start, end):
        #: ``datetime.date``. Start of the range.
        self.start = start
        #: ``datetime.date``. End of the range.
        self.end = end

    def __repr__(self):
        start_date_str = self.start.strftime('%Y/%m/%d') if self.start.year > 1900 else 'MINDATE'
        return '<%s %s - %s>' % (type(self).__name__, start_date_str, self.end.strftime('%Y/%m/%d'))

    def __bool__(self):
        return self.start <= self.end

    def __and__(self, other):
        maxstart = max(self.start, other.start)
        minend = min(self.end, other.end)
        return DateRange(maxstart, minend)

    def __eq__(self, other):
        if not isinstance(other, DateRange):
            raise TypeError()
        return type(self) == type(other) and self.start == other.start and self.end == other.end

    def __ne__(self, other):
        return not self == other

    def __contains__(self, date):
        return self.start <= date <= self.end

    def __iter__(self):
        yield from iterdaterange(self.start, self.end)

    def __hash__(self):
        return hash((self.start, self.end))

    def around(self, date):
        """Returns a date range of the same type as ``self`` that contains ``new_date``.

        Some date ranges change when new transactions are beind added or changed. This is where
        it happens. Returns a new adjusted date range.

        For a non-navigable range, returns ``self``.
        """
        return self

    def next(self):
        """Returns the next range if navigable.

        For example, if we're a month range, return a range with start and end increased by a month.
        """
        return self

    def prev(self):
        """Returns the previous range if navigable.

        For example, if we're a month range, return a range with start and end decreased by a month.

        We make a bit of an exception for this method and implement it in all ranges, rather than
        only navigable ones. This is because it's used in the profit report for the "Last" column
        (we want to know what our results were for the last date range). Some ranges, although not
        navigable, can return a meaningful result here, like :class:`YearToDateRange`, which can
        return the same period last year. Others, like :class:`AllTransactionsRange`, have nothing
        to return, so they return an empty range.
        """
        return self

    def with_new_args(self, **kwargs):
        """Returns the date range with new args ``kwargs``.

        If args aren't applicable or if they haven't changed, return an
        unchanged ``self``.

        We have two args: ``year_start_month`` and ``ahead_months``.
        """
        return self

    @property
    def can_navigate(self):
        """Returns whether this range is navigable.

        In other words, if it's possible to use prev/next to navigate in date ranges.
        """
        return False

    @property
    def days(self):
        """The number of days in the date range."""
        return (self.end - self.start).days + 1

    @property
    def future(self):
        """The future part of the date range.

        That is, the part of the range that is later than today.
        """
        today = date.today()
        if self.start > today:
            return self
        else:
            return DateRange(today + ONE_DAY, self.end)

    @property
    def past(self):
        """The past part of the date range.

        That is, the part of the range that is earlier than today.
        """
        today = date.today()
        if self.end < today:
            return self
        else:
            return DateRange(self.start, today)


class NavigableDateRange(DateRange):
    """A navigable date range.

    Properly implements navigation-related methods so that subclasses don't have to.

    Subclasses :class:`DateRange`.
    """
    def around(self, date):
        return type(self)(date)

    def next(self):
        return self.around(self.end + ONE_DAY)

    def prev(self):
        return self.around(self.start - ONE_DAY)

    @property
    def can_navigate(self): # if it's possible to use prev/next to navigate in date ranges
        return True


class MonthRange(NavigableDateRange):
    """A navigable date range lasting one month.

    ``seed`` is a date for the range to wrap around.

    A monthly range always starts at the first of the month and ends at the last day of that same
    month.

    Subclasses :class:`NavigableDateRange`.
    """
    def __init__(self, seed):
        if isinstance(seed, DateRange):
            seed = seed.start
        month = seed.month
        year = seed.year
        days_in_month = monthrange(year, month)[1]
        start = date(year, month, 1)
        end = date(year, month, days_in_month)
        DateRange.__init__(self, start, end)

    @property
    def display(self):
        """String representation of the range (ex: "July 2013")."""
        return self.start.strftime('%B %Y')


class QuarterRange(NavigableDateRange):
    """A navigable date range lasting one quarter.

    ``seed`` is a date for the range to wrap around.

    A quarterly range always starts at the first day of the first month of the quarter and ends at
    the last day of the last month of that same quarter.

    Subclasses :class:`NavigableDateRange`.
    """
    def __init__(self, seed):
        if isinstance(seed, DateRange):
            seed = seed.start
        month = seed.month
        year = seed.year
        first_month = (month - 1) // 3 * 3 + 1
        last_month = first_month + 2
        days_in_last_month = monthrange(year, last_month)[1]
        start = date(year, first_month, 1)
        end = date(year, last_month, days_in_last_month)
        DateRange.__init__(self, start, end)

    @property
    def display(self):
        """String representation of the range (ex: "Q2 2013")."""
        return tr('Q{0} {1}').format(self.start.month // 3 + 1, self.start.year)


class YearRange(NavigableDateRange):
    """A navigable date range lasting one year.

    ``seed`` is a date for the range to wrap around.

    We can specify ``year_start_month`` if we're weird and we want our year to start at a month
    other than January.

    A yearly range always starts at the first day of the first month of the year and ends at
    the last day of the month 11 months later.

    Subclasses :class:`NavigableDateRange`.
    """
    def __init__(self, seed, year_start_month=1):
        assert 1 <= year_start_month <= 12
        if isinstance(seed, DateRange):
            seed = seed.start
        year = seed.year
        if seed.month < year_start_month:
            year -= 1
        start = date(year, year_start_month, 1)
        end = inc_date(start, RepeatType.Yearly, 1) - ONE_DAY
        DateRange.__init__(self, start, end)

    def around(self, date):
        return type(self)(date, year_start_month=self.start.month)

    def next(self):
        return YearRange(inc_date(self.start, RepeatType.Yearly, 1), year_start_month=self.start.month)

    def prev(self):
        return YearRange(inc_date(self.start, RepeatType.Yearly, -1), year_start_month=self.start.month)

    def with_new_args(self, year_start_month=None, **kwargs):
        if year_start_month is not None and year_start_month != self.start.month:
            today = date.today()
            if today in self:
                seed = today
            else:
                seed = self.start
            return type(self)(seed, year_start_month=year_start_month)
        else:
            return self

    @property
    def display(self):
        """String representation of the range (ex: "Jan 2013 - Dec 2013")."""
        return '{0} - {1}'.format(self.start.strftime('%b %Y'), self.end.strftime('%b %Y'))


class YearToDateRange(DateRange):
    """A date range starting at the beginning of the year and ending now.

    We can specify ``year_start_month`` if we're weird and we want our year to start at a month
    other than January.

    A YTD range always starts at the first day of the first month of the year and ends today.

    Subclasses :class:`DateRange`.
    """
    def __init__(self, year_start_month=1):
        start_year = date.today().year
        if date.today().month < year_start_month:
            start_year -= 1
        start = date(start_year, year_start_month, 1)
        end = date.today()
        DateRange.__init__(self, start, end)

    def prev(self):
        start = inc_date(self.start, RepeatType.Yearly, -1)
        end = inc_date(self.end, RepeatType.Yearly, -1)
        return DateRange(start, end)

    def with_new_args(self, year_start_month=None, **kwargs):
        if year_start_month is not None and year_start_month != self.start.month:
            return type(self)(year_start_month=year_start_month)
        else:
            return self

    @property
    def display(self):
        """String representation of the range (ex: "Jan 2013 - Now")."""
        return tr('{0} - Now').format(self.start.strftime('%b %Y'))


def compute_ahead_months(ahead_months):
    assert ahead_months < 12
    if ahead_months == 0:
        return date.today()
    month_range = MonthRange(date.today())
    for _ in range(ahead_months-1):
        month_range = month_range.next()
    return month_range.end

class RunningYearRange(DateRange):
    """A weird date range, spanning one year, with a user-defined buffer around today.

    The goal of this date range is to represent the "current situation", spanning one year. We want
    to see a bit in the future (to forecast stuff) and a bit in the past, for introspection.

    The ``ahead_months`` preference tells us where we place our year compared to today's date. This
    preference is the number of months we want to see in the future. ``0`` means "stop the range
    at the end of the current month", ``1`` means "stop the range at the end of the next month", and
    so on.

    Once we know our end point, then we know our start point, which is exactly one year earlier.

    Subclasses :class:`DateRange`.
    """
    def __init__(self, ahead_months):
        end = compute_ahead_months(ahead_months)
        end_plus_one = end + ONE_DAY
        start = end_plus_one.replace(year=end_plus_one.year-1)
        if start.day != 1:
            start = inc_date(start, RepeatType.Monthly, 1).replace(day=1)
        DateRange.__init__(self, start, end)
        self.ahead_months = ahead_months

    def prev(self):
        start = self.start.replace(year=self.start.year - 1)
        end = self.start - ONE_DAY
        return DateRange(start, end)

    def with_new_args(self, ahead_months=None, **kwargs):
        if ahead_months is not None and ahead_months != self.ahead_months:
            return type(self)(ahead_months)
        else:
            return self

    @property
    def display(self):
        """String representation of the range (ex: "Running year (Jun - May)")."""
        return tr('Running year ({0} - {1})').format(self.start.strftime('%b'), self.end.strftime('%b'))


class AllTransactionsRange(DateRange):
    """A range big enough to show all transactions (+ ``ahead_months``).

    Date ranges don't know anything about transactions, so those limit dates have to be supplied
    "manually". In the spirit of :class:`RunningYearRange`, we go ahead of the last transaction by
    ``ahead_months`` months.
    """
    def __init__(self, first_date, last_date, ahead_months):
        start = first_date
        end = max(last_date, compute_ahead_months(ahead_months))
        DateRange.__init__(self, start, end)
        self.ahead_months = ahead_months

    def around(self, date):
        first_date = min(self.start, date)
        last_date = max(self.end, date)
        result = AllTransactionsRange(
            first_date=first_date, last_date=last_date, ahead_months=self.ahead_months
        )
        if result == self:
            result = self
        return result

    def prev(self):
        start = self.start - ONE_DAY
        return DateRange(start, start) # whatever, as long as there's nothing in it

    def with_new_args(self, ahead_months=None, **kwargs):
        if ahead_months is not None and ahead_months != self.ahead_months:
            return type(self)(self.start, self.end, ahead_months)
        else:
            return self

    @property
    def display(self):
        """String representation of the range. Always "All Transactions"."""
        return tr("All Transactions")


class CustomDateRange(DateRange):
    """A date range with limits of the user's choosing.

    ``format_func`` is needed for :attr:`display`, which is depnds on the user locale.
    """
    def __init__(self, start, end, format_func):
        DateRange.__init__(self, start, end)
        self._format_func = format_func

    def prev(self):
        end = self.start - ONE_DAY
        start = end - (self.end - self.start)
        return CustomDateRange(start, end, self._format_func)

    @property
    def display(self):
        """String representation of the range (ex: "01-01-2013 - 15-01-2013")."""
        return '{0} - {1}'.format(self._format_func(self.start), self._format_func(self.end))

# --- Date Incrementing

class RepeatType:
    """Available repetition types for :class:`Recurrence`.

    * ``Daily``
    * ``Weekly``
    * ``Monthly``
    * ``Yearly``
    * ``Weekday`` (every 2nd friday of the month)
    * ``WeekdayLast`` (every last friday of the month)
    """
    Daily = 'daily'
    Weekly = 'weekly'
    Monthly = 'monthly'
    Yearly = 'yearly'
    Weekday = 'weekday'
    WeekdayLast = 'weekday_last'
    ALL = {Daily, Weekly, Monthly, Yearly, Weekday, WeekdayLast}

# --- Date Formatting
# For the functions below, the format used is a subset of the Unicode format type
# http://unicode.org/reports/tr35/tr35-6.html#Date_Format_Patterns
# Only the basics are supported: /-. yyyy yy MM M dd d
# anything else in the format should be cleaned out *before* using parse and format

# Why not just convert the Unicode format to strftime's format? Because the strftime formatting
# does not support padding-less month and day.

re_separators = re.compile(r'/|-|\.| ')

def clean_format(format):
    """Removes any format element that is not supported.

    If the result is an invalid format, return a fallback format.

    :param format: ``str``
    :rtype: str
    """
    format = DateFormat(format)
    format.make_numerical()
    return format.iso_format

def parse_date(string, format):
    """Parses ``string`` into a ``datetime.date`` using ``format`` (ISO).

    .. seealso:: :class:`DateFormat`
    """
    return DateFormat(format).parse_date(string)

def format_date(date, format):
    """Formats ``date`` using ``format`` (ISO).

    .. seealso:: :class:`DateFormat`
    """
    return format_year_month_day(date.year, date.month, date.day, format)

def format_year_month_day(year, month, day, format):
    result = format.replace('yyyy', str(year))
    result = result.replace('yy', str(year)[-2:])
    result = result.replace('MM', '%02d' % month)
    result = result.replace('M', '%d' % month)
    result = result.replace('dd', '%02d' % day)
    result = result.replace('d', '%d' % day)
    return result

class DateFormat:
    """Bridge "system" date formats (``%d-%m-%Y``) and "ISO" date formats (``dd-MM-yyyy``).

    We only support simple short and numerical date formats, but we can freely convert each of them
    from/to iso/sys, which is rather convenient.

    This class also supports date format inputs with a moderate amount of garbage in it. It looks
    for a separator, a day, a month and a year element, checks their order and precision, and
    ignores the rest. In case of an unreadable format, it defaults to ``dd/MM/yyyy``.

    The default initialization takes an ISO format. If you want to create a date format from a sys
    format, use :meth:`from_sysformat`.
    """
    ISO2SYS = {'yyyy': '%Y', 'yy': '%y', 'MMM': '%b', 'MM': '%m', 'M': '%m', 'dd': '%d', 'd': '%d'}
    SYS2ISO = {'%Y': 'yyyy', '%y': 'yy', '%m': 'MM', '%b': 'MMM', '%d': 'dd'}

    def __init__(self, format):
        if format is None:
            format = ''
        # Default values in case we can't parse
        self.separator = '/'
        self.elements = ['dd', 'MM', 'yyyy']
        m_separators = re_separators.search(format)
        if m_separators:
            self.separator = m_separators.group()
            elements = format.split(self.separator)
            # macOS (and possibly others) use 'y' to denote the year with a non-zero filled century.
            # Since there is no % equivalent, we'll just use 'yyyy' here instead.
            elements = ['yyyy' if x == 'y' else x for x in elements]
            if all(elem in self.ISO2SYS for elem in elements):
                self.elements = elements

    @staticmethod
    def from_sysformat(format):
        """Creates a new instance from a "sys" format (``%d-%m-%Y``)."""
        if format is None:
            format = ''
        for key, value in DateFormat.SYS2ISO.items():
            format = format.replace(key, value)
        return DateFormat(format)

    def copy(self):
        """Returns a copy of self."""
        return DateFormat(self.iso_format)

    def parse_date(self, string):
        """Parses ``string`` to a ``datetime.date``."""
        # From ticket #381, in some cases the user may input a date field which is in an
        # intermediate editing state such as '1 /12/2012'. They may either accept that or continue
        # to edit to another valid date such as '12/12/2012'. Instead of trying to make the system
        # communicate the end of editing back to the UI level, we simply remove the spurious space
        # characters in the model.
        if self.separator == ' ':
            # In instances where the separator is a space, we can not remove all space characters.
            # Instead, we replace double spaces with a single space.
            string = string.replace('  ', ' ')
        else:
            string = string.replace(' ', '')
        return datetime.strptime(string, self.sys_format).date()

    def make_numerical(self):
        """If the date format contains a non-numerical month, change it to a numerical one."""
        if 'MMM' in self.elements:
            self.elements[self.elements.index('MMM')] = 'MM'

    @property
    def iso_format(self):
        """Returns the format as ISO (``dd-MM-yyyy``)."""
        return self.separator.join(self.elements)

    @property
    def sys_format(self):
        """Returns the format as sys (``%d-%m-%Y``)."""
        repl_elems = [self.ISO2SYS[elem] for elem in self.elements]
        return self.separator.join(repl_elems)
