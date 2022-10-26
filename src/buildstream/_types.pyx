#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Jim MacArthur <jim.macarthur@codethink.co.uk>
#        Benjamin Schubert <bschubert15@bloomberg.net>

# MetaFastEnum()
#
# This is a reemplementation of MetaEnum, in order to get a faster implementation of Enum.
#
# Enum turns out to be very slow and would add a noticeable slowdown when we try to add them to the codebase.
# We therefore reimplement a subset of the `Enum` functionality that keeps it compatible with normal `Enum`.
# That way, any place in the code base that access a `FastEnum`, can normally also accept an `Enum`. The reverse
# is not correct, since we only implement a subset of `Enum`.
class MetaFastEnum(type):
    def __new__(mcs, name, bases, dct):
        if name == "FastEnum":
            return type.__new__(mcs, name, bases, dct)

        assert len(bases) == 1, "Multiple inheritance with Fast enums is not currently supported."

        dunder_values = {}
        normal_values = {}

        parent_keys = bases[0].__dict__.keys()

        assert "__class__" not in dct.keys(), "Overriding '__class__' is not allowed on 'FastEnum' classes"

        for key, value in dct.items():
            if key.startswith("__") and key.endswith("__"):
                dunder_values[key] = value
            else:
                assert key not in parent_keys, "Overriding 'FastEnum.{}' is not allowed. ".format(key)
                normal_values[key] = value

        kls = type.__new__(mcs, name, bases, dunder_values)
        mcs.set_values(kls, normal_values)

        return kls

    @classmethod
    def set_values(mcs, kls, data):
        value_to_entry = {}

        assert len(set(data.values())) == len(data.values()), "Values for {} are not unique".format(kls)
        assert len(set(type(value) for value in data.values())) <= 1, \
            "Values of {} are of heterogeneous types".format(kls)

        for key, value in data.items():
            new_value = object.__new__(kls)
            object.__setattr__(new_value, "value", value)
            object.__setattr__(new_value, "name", key)

            type.__setattr__(kls, key, new_value)

            value_to_entry[value] = new_value

        type.__setattr__(kls, "_value_to_entry", value_to_entry)

    def __repr__(self):
        return "<fastenum '{}'>".format(self.__name__)

    def __setattr__(self, key, value):
        raise AttributeError("Adding new values dynamically is not supported")

    def __iter__(self):
        return iter(self._value_to_entry.values())
