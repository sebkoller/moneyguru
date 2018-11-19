import _ccore

_ccore.currency_global_init("bar.db")
_ccore.currency_register("foo", 2)
print(repr(_ccore.Currency('foo')))
