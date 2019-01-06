# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from .base import ViewChild

class ChartView:
    """Expected interface for :class:`Chart`'s view.

    *Not actually used in the code. For documentation purposes only.*

    Our view, a rectangular widget in which we can draw, is expected to respond to all drawing
    methods defined here by performing the drawing on itself.

    It is expected to define a pen, a brush and a font for every constant defined in the core.
    """
    def draw_line(self, p1, p2, pen_id):
        """Draw a line from ``p1`` to ``p2`` using pen ``pen_id``.

        :param .geometry.Point p1: Start point
        :param .geometry.Point p2: End point
        :param int pen_id: Pen to use
        """

    def draw_rect(self, rect, pen_id, brush_id):
        """Draw a rectangle ``rect`` using ``pen_id`` and ``brush_id``.

        :param .geometry.Rect rect: Rectangle coordinates
        :param int pen_id: Pen to use
        :param int brush_id: Brush to use
        """

    def draw_pie(self, center, radius, start_angle, span_angle, brush_id):
        """Draw a pie slice.

        A pie slice is a slice of a circle of a given ``radius`` and ``center``, with a
        ``start_angle`` and a ``span_angle``.


        :param .geometry.Point center: Center of the circle
        :param int radius: Radius of the circle
        :param float start_angle: Angle (degrees) at which we start our pie. ``0`` is the rightmost
                                  part of the circle.
        :param float span_angle: Angle (degrees) representing the width of our pie. We span
                                 counter-clockwise.
        :param int brush_id: Brush to use
        """

    def draw_polygon(self, points, pen_id, brush_id):
        """Draw a polygon of an arbitrary shape.

        :param points: List of :class:`.geometry.Point` in the polygon. The first and last
                       points are automatically joined by a direct line to close the shape.
        :param int pen_id: Pen to use
        :param int brush_id: Brush to use
        """

    def draw_text(self, text, rect, font_id):
        """Draw ``text`` in ``rect``.

        The manner in which the text is managed inside the ``rect`` (line wrapping, clipping, etc.)
        depends on the UI layer, which can have different behaviors for different ``font_id``.

        :param str text: Text to draw
        :param .geometry.Rect rect: Rectangle coordinates
        :param int font_id: Font (and related draw attributes) to use
        """

    def text_size(self, text, font_id):
        """Returns the size of ``text`` for ``font_id``.

        :param str text: Text to query for
        :param int font_id: Font to use
        :returns: ``(width, height)``
        """

class Chart(ViewChild):
    """Base abstract class for all charts.

    Charts are widgets that are "manually" drawn using conventional vector graphic drawing methods.
    Because we're in a cross toolkit environment, we can't use any specific API, so we made our own
    (and simplified) API to talk to the UI layer.

    The coordinates used in this API are related to the view size, which is given to us by the UI
    layer. Those coordinates are also bottom-left based, that is, the origin ``(0, 0)`` is at the
    top-bottom corner. For example, if the UI tells us that our view is 100x100, then the
    coordinates for a rectangle that takes a quarter of our view and is at the bottom left would be
    ``(0, 0, 25, 25)``.

    *Colors and fonts.* The details of how colors, pen size, brush size and fonts are handled is the
    responsibility of UI layers. In the core layers, we only deal in IDs. Every aspect of the graph
    has its ID, which is a simple numerical ID. For example, we have a ID for main axis lines. Do
    we want to axis lines to be black and with a 2pt width? Maybe, but that's for the UI layer to
    decide. When we draw our axis, we're telling the UI layer "draw me a line at those coordinates
    using the pen for main axis lines".

    Subclasses :class:`.ViewChild`.
    """

    def __init__(self, parent_view):
        ViewChild.__init__(self, parent_view)
        self.view_size = (0, 0)

    # --- Override
    def _revalidate(self):
        self.compute()
        self.view.refresh()

    # --- Virtual
    def compute(self):
        """*Virtual.* Re-compute the charts data points to be drawn."""
        raise NotImplementedError()

    def draw(self):
        """Draw the chart."""
        if self.has_view():
            self.draw_chart()

    # --- Public
    def set_view_size(self, width, height):
        """Changes the size of the view to draw our chart into."""
        self.view_size = (width, height)

    # --- Properties
    @property
    def data(self):
        """List of data points to be drawn.

        The format of those data points depends on the chart type. This is re-computed whenever
        our underlying data changes.

        This property is mostly there for historical reasons. In early versions of moneyGuru,
        drawing wasn't driven by the core, but by UI layers. This property was feeding the UI layer
        with data points to draw.
        """
        return self._data

    @property
    def title(self):
        """Title of the chart."""
        return ''

    @property
    def currency(self):
        """Currency used in the chart's datapoints."""
        return self.document.default_currency

