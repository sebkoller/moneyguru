=============================================
moneyGuru API
=============================================

This part of the documentation describes classes seen in moneyGuru's code, every class being
described individually. If you haven't already, you might want to read the :doc:`overview of
moneyGuru's architecture <../architecture>`. This documentation is not complete and only include
core elements of the API. The reason for this is that moneyGuru's code evolves fairly quickly and
keeping up with every little details of the API is not worth it, IMO. However, with this
documentation, it should normally be possible for someone new to the code to dig in it and figure
out, from the code, what everything is about.

**Code in ccore is not present in this documentation.** To see documentation of
classes that have been rewritten to C, refer to source code directly.

.. toctree::
    :maxdepth: 2
    :glob:
    
    app
    document
    plugin
    model/*
    gui/*
