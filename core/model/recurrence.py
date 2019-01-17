# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import copy
import datetime
from calendar import monthrange
from itertools import chain

from core.util import nonone, first
from core.trans import tr

from ._ccore import Transaction, inc_date
from .date import RepeatType

def find_schedule_of_ref(ref, schedules):
    return first(s for s in schedules if s.contains_ref(ref))

ONE_DAY = datetime.timedelta(1)

class DateCounter:
    """Iterates over dates in a regular manner.

    This is an iterator, so once we've created our DateCounter, we simply iterate over it to get our
    dates (we yield ``datetime.date`` instances).

    Sometimes (well, only with ``RepeatType.Weekday``), we have to skip a beat. If, for example, we
    have to return the 5th friday of the month and that our current month doesn't have it, we skip
    it and return the first month to have it. So, sometimes, we can have big gap in between our
    dates.

    :param base_date: Date from which we start our iteration. For weekly repeat types, this date
                      also determines which weekday we're looking for in our next dates. If our base
                      date is the 2nd friday of its month, then we're going to iterate over all 2nd
                      friday of months.
    :type base_date: datetime.date
    :param repeat_type: The type of interval we want to put in between our yielded dates.
    :type repeat_type: :class:`RepeatType`
    :param int repeat_every: Amplitude of the interval to put in between our dates. For example,
                             with a monthly repeat type, ``3`` would mean "every 3 months". For
                             "weekday" types, ``repeat_every`` is also in months.
    :param datetime.date end: Date at which to stop the iteration.

    .. seealso:: :doc:`/forecast`
    """
    def __init__(self, base_date, repeat_type, repeat_every, end):
        self.base_date = base_date
        self.end = end
        self.inccount = 0
        self.repeat_type = repeat_type
        self.incsize = repeat_every
        self.current_date = None

    def __iter__(self):
        return self

    def __next__(self):
        # It's possible for a DateCounter to be created with an end date smaller than its start
        # date. In this case, simply never yield any date.
        if self.base_date > self.end:
            raise StopIteration()
        if self.current_date is None: # first date of the iteration is base_date
            self.current_date = self.base_date
            return self.current_date
        new_date = None
        while new_date is None:
            self.inccount += self.incsize
            new_date = inc_date(self.base_date, self.repeat_type, self.inccount)
        if new_date <= self.current_date or new_date > self.end:
            raise StopIteration()
        self.current_date = new_date
        return new_date


def Spawn(recurrence, ref, recurrence_date, date=None, txntype=2):
    date = date or recurrence_date
    res = Transaction(
        txntype, date, ref.description, ref.payee, ref.checkno, None, None)
    #: ``datetime.date``. Date at which the spawn is "supposed to happen", which can be
    #: overridden by the ``date`` argument, if we're in an "exception" situation. We need to
    #: keep track of this date because it's used as a kind of ID (oh, the spawn
    #: ``schedule42@03-04-2014``? Yeah, there's an exception for that one) in the save file.
    res.recurrence_date = recurrence_date
    #: :class:`.Transaction`. Template transaction for our spawn. Most of the time, it's the
    #: same as :attr:`Recurrence.ref`, unless we have an "exception" in our schedule.
    res.ref = ref
    res.change(splits=ref.splits)
    for split in res.splits:
        split.reconciliation_date = None
    res.balance()
    return res


class Recurrence:
    """A recurring transaction (called "Schedule" in the app).

    .. rubric:: Schedule exceptions

    One of the great features of moneyGuru is its ability to easy allow exceptions in its schedule.
    The amount changes one month? No problem, just change it. The transaction happens a day later?
    No problem, change it. From now on, every following transaction is going to happen a day later?
    No problem, hold shift when you commit the change to make it "global".

    All these exceptions, they have to be recorded somewhere. The "one-time" exceptions are kept in
    :attr:`date2exception`. The date used in the mapping is :attr:`Spawn.recurrent_date` because
    when we change the date of an exception, we still want to remember which recurrent date it
    replaces, so we used the date at which the *regular* transaction was supposed to happen.

    There are also the "global" exceptions, which are stored in :attr:`date2globalchange` and work
    kinda like normal exception, except that from the date they first happen, all following spawns
    are going to use this exception as a transaction model. This includes date. That is, if a global
    exception is 3 days later than its :attr:`Spawn.recurrent_date`, then all following spawns are
    going to to be 3 days later.

    Exceptions can override each other. We can be riding on a global exception and, suddenly, a
    newer global or local exception is there! Well, we apply that exception.

    An exception can also be a deletion, that is "oh, this week that transaction didn't happen".
    This is recorded by putting ``None`` in :attr:`date2exception`. When this deletion is done as
    a global change (from this date, this recurrence doesn't happen anymore), we simply set
    :attr:`stop_date`.

    .. seealso:: :class:`DateCounter`

    :param ref: See :attr:`ref`
    :type ref: :class:`.Transaction`
    :param repeat_type: The type of interval we have in between spawns.
    :type repeat_type: :class:`RepeatType`
    :param int repeat_every: The amplitude of that repetition.
    """
    def __init__(self, ref, repeat_type, repeat_every):
        if repeat_type not in RepeatType.ALL:
            # invalid repeat type, default to monthly
            repeat_type = RepeatType.Monthly
        #: :class:`.Transaction`. The model transaction that's going to be regularly spawned.
        self.ref = ref
        self._repeat_type = repeat_type
        self._repeat_every = repeat_every
        #: Date at which our recurrence stops. When ``None`` (the default), it never ends.
        self.stop_date = None
        #: ``recurrent_date -> transaction`` mapping of schedule exceptions.
        self.date2exception = {}
        #: ``recurrent_date -> transaction`` mapping of *global* schedule exceptions.
        self.date2globalchange = {}
        #: ``recurrent_date -> transaction`` mapping of spawns. Used as a cache. Frequently purged.
        self.date2instances = {}
        self.rtype2desc = {
            RepeatType.Daily: tr('Daily'),
            RepeatType.Weekly: tr('Weekly'),
            RepeatType.Monthly: tr('Monthly'),
            RepeatType.Yearly: tr('Yearly'),
            RepeatType.Weekday: '', # dynamic
            RepeatType.WeekdayLast: '', # dynamic
        }
        self._update_rtype_descs()

    def __repr__(self):
        return '<Recurrence %s %d>' % (self.repeat_type, self.repeat_every)

    # --- Private
    def _all_exceptions(self):
        exceptions = chain(self.date2exception.values(), self.date2globalchange.values())
        return (e for e in exceptions if e is not None)

    def _create_spawn(self, ref, date):
        return Spawn(self, ref, date)

    def _update_ref(self):
        # Go through our recurrence dates and see if we should either move our start date due to
        # deleted spawns or to update or ref transaction due to a global change that end up being
        # on our first recurrence date.
        date_counter = DateCounter(self.start_date, self.repeat_type, self.repeat_every, datetime.date.max)
        for d in date_counter:
            if d in self.date2exception and self.date2exception[d] is None:
                continue
            if d in self.date2globalchange:
                self.ref = self.date2globalchange[d].replicate()
            else:
                self.ref.date = d
            break
        self.date2exception = {d: ex for d, ex in self.date2exception.items() if d > self.start_date}
        self.date2globalchange = {d: ex for d, ex in self.date2globalchange.items() if d > self.start_date}
        self.reset_spawn_cache()
        self._update_rtype_descs()

    def _update_rtype_descs(self):
        date = self.start_date
        weekday_name = date.strftime('%A')
        week_no = (date.day - 1) // 7
        position = [tr('first'), tr('second'), tr('third'), tr('fourth'), tr('fifth')][week_no]
        self.rtype2desc[RepeatType.Weekday] = tr('Every %s %s of the month') % (position, weekday_name)
        _, days_in_month = monthrange(date.year, date.month)
        if days_in_month - date.day < 7:
            self.rtype2desc[RepeatType.WeekdayLast] = tr('Every last %s of the month') % weekday_name
        else:
            self.rtype2desc[RepeatType.WeekdayLast] = ''

    # --- Public
    def affected_accounts(self):
        """Returns a set of all :class:`.Account` affected by the schedule.

        This is pretty much the same as calling
        :meth:`~core.model.transaction.Transaction.affected_accounts` on :attr:`ref`, except that it
        also checks in exception instances to make there there isn't another affected account in
        there.
        """
        result = self.ref.affected_accounts()
        for exception in self._all_exceptions():
            result |= exception.affected_accounts()
        return result

    def change_globally(self, spawn):
        """Add a user-modified spawn into the global exceptions list.

        :param spawn: The spawn to add to :attr:`date2globalchange`.
        :type spawn: :class:`.Spawn`
        """
        for date in list(self.date2globalchange.keys()):
            if date >= spawn.recurrence_date:
                del self.date2globalchange[date]
        for date, exception in list(self.date2exception.items()):
            # we don't want to remove local deletions
            if exception is not None and date >= spawn.recurrence_date:
                del self.date2exception[date]
        self.date2globalchange[spawn.recurrence_date] = spawn
        self._update_ref()

    def contains_ref(self, ref):
        if self.ref == ref:
            return True
        if ref in self.date2globalchange.values():
            return True
        if ref in self.date2instances.values():
            return True
        return False

    def delete(self, spawn):
        """Create an exception that prevents ``spawn`` from spawning again.

        :param spawn: The spawn to delete.
        :type spawn: :class:`Spawn`
        """
        self.delete_at(spawn.recurrence_date)

    def delete_at(self, date):
        """Create an exception that prevents further spawn at ``date``."""
        self.date2exception[date] = None
        self._update_ref()

    def get_spawns(self, end):
        """Returns the list of transactions spawned by our recurrence.

        We start at :attr:`start_date` and end at ``end``. We have to specify an end to our spawning
        to avoid getting infinite results.

        .. rubric:: End date adjustment

        If a changed date end up being smaller than the "spawn date", it's possible that a spawn
        that should have been spawned for the date range is not spawned. Therefore, we always
        spawn at least until the date of the last exception. For global changes, it's even more
        complicated. If the global date delta is negative enough, we can end up with a spawn that
        doesn't go far enough, so we must adjust our max date by this delta.

        :param datetime.date end: When to stop spawning.
        :rtype: list of :class:`Spawn`
        """
        if self.date2exception:
            end = max(end, max(self.date2exception.keys()))
        if self.date2globalchange:
            min_date_delta = min(ref.date-date for date, ref in self.date2globalchange.items())
            if min_date_delta < datetime.timedelta(days=0):
                end += -min_date_delta
        end = min(end, nonone(self.stop_date, datetime.date.max))

        date_counter = DateCounter(self.start_date, self.repeat_type, self.repeat_every, end)
        result = []
        global_date_delta = datetime.timedelta(days=0)
        current_ref = self.ref
        for current_date in date_counter:
            if current_date in self.date2globalchange:
                current_ref = self.date2globalchange[current_date]
                global_date_delta = current_ref.date - current_date
            if current_date in self.date2exception:
                exception = self.date2exception[current_date]
                if exception is not None:
                    result.append(exception)
            else:
                if current_date not in self.date2instances:
                    spawn = self._create_spawn(current_ref, current_date)
                    if global_date_delta:
                        # Only muck with spawn.date if we have a delta. otherwise we're breaking
                        # budgets.
                        spawn.date = current_date + global_date_delta
                    self.date2instances[current_date] = spawn
                result.append(self.date2instances[current_date])
        return result

    def reassign_account(self, account, reassign_to=None):
        """Reassigns accounts for :attr:`ref` and all exceptions.

        .. seealso:: :meth:`affected_accounts`
                     :meth:`~core.model.transaction.Transaction.reassign_account`
        """
        self.ref.reassign_account(account, reassign_to)
        for exception in self._all_exceptions():
            exception.reassign_account(account, reassign_to)
        self.reset_spawn_cache()

    def replicate(self):
        """Returns a copy of ``self``."""
        result = copy.copy(self)
        result.date2exception = copy.copy(self.date2exception)
        result.date2globalchange = copy.copy(self.date2globalchange)
        result.date2instances = {}
        result.ref = self.ref.replicate()
        return result

    def reset_exceptions(self):
        """Empties :attr:`date2exception` and :attr:`date2globalchange`."""
        self.date2exception = {}
        self.date2globalchange = {}

    def reset_spawn_cache(self):
        """Empties :attr:`date2instances`."""
        self.date2instances = {}

    def stop_at(self, spawn):
        """Stop further spawning at ``spawn`` (sets :attr:`stop_date`)."""
        self.stop_date = spawn.recurrence_date

    def stop_before(self, spawn):
        """Stop further spawning just before ``spawn`` (sets :attr:`stop_date`)."""
        self.stop_date = spawn.recurrence_date - ONE_DAY

    # --- Properties
    @property
    def is_alive(self):
        """Returns whether :meth:`get_spawns` can ever return anything."""
        if self.stop_date is None:
            return True
        return bool(self.get_spawns(self.stop_date))

    @property
    def repeat_every(self):
        """``int``. See :class:`DateCounter`."""
        return self._repeat_every

    @repeat_every.setter
    def repeat_every(self, value):
        if value == self._repeat_every:
            return
        self._repeat_every = value
        self.reset_exceptions()

    @property
    def repeat_type(self):
        """:class:`RepeatType`. See :class:`DateCounter`."""
        return self._repeat_type

    @repeat_type.setter
    def repeat_type(self, value):
        if value == self._repeat_type:
            return
        self._repeat_type = value
        self.reset_exceptions()

    @property
    def repeat_type_desc(self):
        """``str``. User-readable description of our :attr:`repeat_type`.

        Things like "Daily" and "Weekly". For "Weekday" repeat types, the description is dynamic
        (depending on :attr:`start_date`) and looks like "Every 2nd friday of the month".
        """
        return self.rtype2desc[self._repeat_type]

    @property
    def start_date(self):
        """``datetime.date``. When our recurrence begins.

        Same as the :attr:`Transaction.date` attribute of :attr:`ref`.
        """
        return self.ref.date

    @start_date.setter
    def start_date(self, value):
        if value == self.ref.date:
            return
        self.ref.date = value
        self.reset_exceptions()
        self._update_rtype_descs()

