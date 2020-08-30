import os
import time
import re
import hashlib
from socket import gethostname
from munch import Munch, munchify


def is_debug_env():
    debug_env = os.environ.get('MISO_DEVELOPMENT', '').strip().lower()
    return debug_env in ('1', 'yes', 'y', 'true', 't')


def hostname(short=True):
    if short:
        return gethostname().split('.')[0]
    else:
        return gethostname()


def safe_filename(fn: str):
    return re.sub(' +', ' ', "".join([c for c in fn if c.isalpha() or c.isdigit() or c in '[]_-. ']).rstrip())


def comma_join(join_list: list):
    return ', '.join(join_list)


def ensure_str(str_: bytes):
    """ Ensure the input is a string object, decoding from bytes if necessary (UTF-8 assumed) """
    if isinstance(str_, bytes):
        return str_.decode('utf-8')
    return str_


def ensure_bytes(bytes_: str):
    """ Ensure the input is a bytes object, encoding from string if necessary (UTF-8 assumed) """
    if isinstance(bytes_, str):
        return bytes_.encode('utf-8')
    return bytes_


def first_or_none(pos_list):
    """ Returns the first element of a list, or None if there are no elements """
    if isinstance(pos_list, list) and pos_list:
        return pos_list[0]


def force_list(obj):
    """ If supplied anything other than a list, new list is returned with obj as first element """
    if isinstance(obj, list):
        return obj
    return [obj, ]


def sleep(dur):
    time.sleep(dur)


def epoch(small=True):
    """ Short hand to get current epoch """
    epoch_ = int(time.time() * 1000)
    if small is True:
        epoch_ = epoch_ / 1000
    return epoch_


def md5sum(md5str):
    md5 = hashlib.md5()
    md5.update(ensure_bytes(md5str))
    return str(md5.hexdigest())


def md5file(filename):
    BUF_SIZE = 65536
    md5 = hashlib.md5()

    with open(filename, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            md5.update(data)

    return str(md5.hexdigest())


def automunchify(data):
    return munchify(data, AutoMunch)


class AutoMunch(Munch):
    """ Some addons yet to be included in Infinidat/munch:
        https://github.com/Infinidat/munch/pull/36
    """

    def __setattr__(self, k, v):
        """ Works the same as Munch.__setattr__ but if you supply
            a dictionary as value it will convert it to another Munch.
        """
        if isinstance(v, (AutoMunch, Munch)):
            v = automunchify(v.toDict())
        elif isinstance(v, dict):
            v = automunchify(v)
        elif isinstance(v, list):
            v = [automunchify(li) for li in v]

        super(AutoMunch, self).__setattr__(k, v)


class Result(object):
    """ A service return template object. All services should return one of these so that output
        of microservices remains consistent.
    """

    def __init__(self, data=None, result=None, trace=None, locked=None, reason=None, detail=None):
        self.data = automunchify(data) if data is not None else None
        self.result = result if result is not None else bool(self.data)
        self.reason = reason
        self.detail = detail
        self.trace = trace
        self.locked = locked is True  # We should lock the object if we just deserialised
        if self.trace and not reason:
            self.reason = 'uncaught exception (traceback in service)'

    @property
    def traceback(self):
        """ Returns true if this ServiceResult is an exception """
        return self.result is False and self.trace is not None

    def to_dict(self):
        """ Return the version that should be stored as a dict (for serialization) """
        return {
            'result': self.result,
            'reason': self.reason,
            'data': self.data.toDict() if isinstance(self.data, AutoMunch) else self.data,
            'detail': self.detail.toDict() if isinstance(self.detail, AutoMunch) else self.detail,
            'trace': self.trace
        }

    def __repr__(self):
        short_data = str(self.data.toDict() if isinstance(self.data, AutoMunch) else self.data)
        if len(short_data) > 30:
            short_data = short_data[0:27] + '...'
        if self.traceback:
            last_line = self.trace.strip().split('\n')[-1]
            return f'<Result(result={self.result}, exception={last_line})>'
        else:
            return f'<Result(result={self.result}, data={short_data})>'

    def __getattribute__(self, item):
        real = super().__getattribute__(item)
        if item == 'result':
            real = real if real is not None else self.data is not None
        return real
