# This file is part of the pyMor project (http://www.pymor.org).
# Copyright Holders: Felix Albrecht, Rene Milk, Stephan Rave
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function

from numbers import Number

import numpy as np

from .interfaces import ParameterFunctionalInterface


class ProjectionParameterFunctional(ParameterFunctionalInterface):
    '''`ParameterFunctional` which returns a component of the parameter.

    Parameters
    ----------
    parameter_type
        The parameter type of the parameters the functional takes.
    component
        The component to return.
    coordinates
        If not `None` return `mu[component][coordinates]` instead of
        `mu[component]`.
    name
        Name of the functional.
    '''

    def __init__(self, parameter_name, parameter_shape, coordinates=None, name=None):
        super(ProjectionParameterFunctional, self).__init__()
        self.name = name
        if isinstance(parameter_shape, Number):
            parameter_shape = tuple() if parameter_shape == 0 else (parameter_shape,)
        self.build_parameter_type({parameter_name: parameter_shape}, local_global=True)
        self.parameter_name = parameter_name
        if sum(parameter_shape) > 1:
            assert coordinates is not None and coordinates < parameter_shape
        self.coordinates = coordinates
        self.lock()

    def evaluate(self, mu=None):
        mu = self.parse_parameter(mu)
        if self.coordinates is None:
            return mu[self.parameter_name]
        else:
            return mu[self.parameter_name][self.coordinates]


class GenericParameterFunctional(ParameterFunctionalInterface):
    '''A wrapper making an arbitrary python function a `ParameterFunctional`

    Parameters
    ----------
    parameter_type
        The parameter type of the parameters the functional takes.
    mapping
        The function to wrap. The function is of the form `mapping(mu)`.
    name
        The name of the functional.
    '''

    def __init__(self, mapping, parameter_type, name=None):
        super(ParameterFunctionalInterface, self).__init__()
        self.name = name
        self._mapping = mapping
        self.build_parameter_type(parameter_type, local_global=True)
        self.lock()

    def evaluate(self, mu=None):
        mu = self.parse_parameter(mu)
        return self._mapping(mu)


class ExpressionParameterFunctional(GenericParameterFunctional):

    functions = {k: np.__dict__[k] for k in {'sin', 'cos', 'tan', 'arcsin', 'arccos', 'arctan',
                                             'sinh', 'cosh', 'tanh', 'arcsinh', 'arccosh', 'arctanh',
                                             'exp', 'exp2', 'log', 'log2', 'log10',
                                             'min', 'minimum', 'max', 'maximum',
                                            }}

    def __init__(self, expression, parameter_type, name=None):
        self.expression = expression
        code = compile(expression, '<dune expression>', 'eval')
        mapping = lambda mu: eval(code, self.functions, mu)
        GenericParameterFunctional.__init__(self, mapping, parameter_type, name)

    def __repr__(self):
        return 'ExpressionParameterFunctional({}, {})'.format(self.expression, repr(self.parameter_type))

    def __getstate__(self):
        return (self.expression, self.parameter_type, self.name)

    def __setstate__(self, state):
        self.__init__(*state)
