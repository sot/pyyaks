class ValueException(Exception):
    pass

ValueTypeRegistry = {}

class ValueType(object):
    defaults = {'langtype': 'plain',
                'fmt': 'auto',
                'showunit': False}

    def match(m):
        """ Find the nearest match for m in the ValueType registry."""
        if type(m) is ValueType:
            return m
        # m should be a string at this point
        if m in ValueTypeRegistry:
            return ValueTypeRegistry[m]

        matches = dict((key, vtr) for key, vtr in ValueTypeRegistry.items()
                       if vtr.lower().endswith(m.lower()))
        if not matches:
            raise ValueException, 'Value has no associated format description'

        

    def __init__(match=None,
                 unit=None,
                 mult=None,
                 fmt=None,
                 label='',
                 ):
        self.match = match
        self.mult = mult
        self.label = label

        if unit is None: self.unit = {}
        else: self.unit = unit

        if fmt is None: self.fmt = {}
        else: self.fmt = fmt

    def addfmt(langtype, fmt, fmtstr, args):
        if langtype not in self.fmt:
            self.fmt[langtype] = {}
        self.fmt[langtype][fmt] = (fmtstr, args)


class Value(object):
    def geterr_(self, i):
        if self.__err is None:
            raise ValueException, 'Value has no associated error'
        return self.__err[i]
    def seterr_(self, x, is_):
        if self.__err = None:
            self.__err = (None, None)
        for i in is_:
            self.__err[i] = x

    def geterr(self): return self._geterr(0)
    def seterr(self, x): self._seterr(x, [0,1])
    def geterr_lo(self): return self._geterr(0)
    def seterr_lo(self, x): self._seterr(x, [0])
    def geterr_hi(self): return self._geterr(1)
    def seterr_hi(self, x): self._seterr(x, [1])

    err = property(geterr, seterr)
    err_lo = property(geterr_lo, seterr_lo)
    err_hi = property(geterr_hi, seterr_hi)

    def __init__(self, val, err=None, err_hi=None, valuetype=None):
        self.val = val

        # Set internal error values
        if err is None:
            self.__err = None
        else:
            if err_hi is None:
                self.__err = (err, err)
            else:
                self.__err = (err, err_hi)

        if valuetype is None:
            self.valuetype = ValueType()
        else:
            self.valuetype = ValueType.match(valuetype)

    def render(self, langtype=None, fmt=None):
        pass

    def __str__(self):
        return self.render()
        
