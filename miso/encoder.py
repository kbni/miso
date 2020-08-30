import json
from datetime import datetime, timedelta, date, tzinfo

import pendulum
import pytz
from kombu.serialization import register

from .utils import Result


class JSONEncoder(json.JSONEncoder):
    """
    Converts a python object, where datetime and timedelta objects are converted
    into objects that can be decoded using the DateTimeAwareJSONDecoder.
    """

    def default(self, o):  # pylint: disable=E0202
        if isinstance(o, Result):
            return dict(
                __type__='Result',
                **o.to_dict()
            )
        if isinstance(o, datetime):
            if o.tzinfo and hasattr(o.tzinfo, 'name'):
                return {
                    '__type__': 'datetime',
                    'year': o.year,
                    'month': o.month,
                    'day': o.day,
                    'hour': o.hour,
                    'minute': o.minute,
                    'second': o.second,
                    'microsecond': o.microsecond,
                    'tzinfo': o.tzinfo.name,
                }
            else:
                return {
                    '__type__': 'datetime.isoformat',
                    'isoformat': o.isoformat()
                }
        elif isinstance(o, date):
            return {
                '__type__': 'date',
                'year': o.year,
                'month': o.month,
                'day': o.day
            }
        elif isinstance(o, timedelta):
            return {
                '__type__': 'timedelta',
                'days': o.days,
                'seconds': o.seconds,
                'microseconds': o.microseconds,
            }
        else:
            return json.JSONEncoder.default(self, o)


class JSONDecoder(json.JSONDecoder):
    """
    Converts a json string, where datetime and timedelta objects were converted
    into objects using the DateTimeAwareJSONEncoder, back into a python object.
    """

    def __init__(self):
        json.JSONDecoder.__init__(self, object_hook=self.dict_to_object)

    def dict_to_object(self, dict_):
        """ Convert a dictionary with a __type__ key into special objects """
        if '__type__' not in dict_:
            return dict_

        type_ = dict_.pop('__type__')
        if type_ == 'datetime':
            usetz = dict_.get('tzinfo', None)
            if usetz is not None:
                # If usetz is a string like '+01:00' try to replace with 'Etc/GMT+1'
                if isinstance(usetz, str) and '/' not in usetz:
                    usetz = 'Etc/GMT' + usetz.replace(':00', '').replace('+0', '+').replace('-0', '-')
                dict_['tzinfo'] = pytz.timezone(usetz)

            return pendulum.instance(datetime(**dict_))
        elif type_ == 'datetime.isoformat':
            return pendulum.parse(dict_['isoformat'])
        elif type_ == 'timedelta':
            return timedelta(**dict_)
        elif type_ == 'date':
            return pendulum.date(**dict_)
        elif type_ == 'Result':
            return Result(locked=True, **dict_)
        else:
            # Oops... better put this back together.
            dict_['__type__'] = type_
            return dict_


def loads(data):
    return json.loads(data, cls=JSONDecoder)


def dumps(data, sort_keys=True, indent=2):
    return json.dumps(data, cls=JSONEncoder, sort_keys=sort_keys, indent=indent)


def register_better_json():
    """ Register this serializer for use throughout our nameko project """
    register('betterjson', JSONEncoder().encode, JSONDecoder().decode, 'application/x-better-json', 'utf-8')
