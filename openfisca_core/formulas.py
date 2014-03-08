# -*- coding: utf-8 -*-


# OpenFisca -- A versatile microsimulation software
# By: OpenFisca Team <contact@openfisca.fr>
#
# Copyright (C) 2011, 2012, 2013, 2014 OpenFisca Team
# https://github.com/openfisca
#
# This file is part of OpenFisca.
#
# OpenFisca is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# OpenFisca is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import logging

import numpy as np


log = logging.getLogger(__name__)


class AbstractFormula(object):
    holder = None

    def __init__(self, holder = None):
        assert holder is not None
        self.holder = holder


class AbstractSimpleFormula(AbstractFormula):
    individual_roles_by_parameter = None  # TODO Remove this and _option and replace with a call to function convert_column_from_entity_to_person in formula function.
    parameters = None
    requires_default_legislation = False
    requires_legislation = False
    requires_self = False

    def __init__(self, holder = None):
        super(AbstractSimpleFormula, self).__init__(holder = holder)

        function = self.calculate
        code = function.__code__
        self.parameters = parameters = list(code.co_varnames[:code.co_argcount])
        # Check whether default legislation is used by function.
        if '_defaultP' in parameters:
            self.requires_default_legislation = True
            parameters.remove('_defaultP')
        # Check whether current legislation is used by function.
        if '_P' in parameters:
            self.requires_legislation = True
            parameters.remove('_P')
        # Check whether individual roles are given to some parameters.
        if '_option' in parameters:
            parameters.remove('_option')
            self.individual_roles_by_parameter = function.func_defaults[0]
            for parameter in self.individual_roles_by_parameter:
                assert parameter in parameters, \
                    'Parameter {} in individual_roles_by_parameter but not in function parameters'.format(parameter)
        # Check whether function uses self (aka formula).
        if 'self' in parameters:
            self.requires_self = True
            parameters.remove('self')

    def __call__(self, requested_columns_name = None):
        holder = self.holder
        column = holder.column
        entity = holder.entity
        simulation = entity.simulation
        individus = simulation.entities['individus']
        tax_benefit_system = simulation.tax_benefit_system

        if requested_columns_name is None:
            requested_columns_name = set()
        else:
            assert column.name not in requested_columns_name, 'Infinite loop. Missing values for columns: {}'.format(
                u', '.join(sorted(requested_columns_name)).encode('utf-8'))

        if holder.array is not None:
            return holder
#        if holder.disabled:
#            return holder

        requested_columns_name.add(holder.column.name)
        required_parameters = set(self.parameters)
        arguments = {}
        arguments_holder = []
        individual_roles_by_parameter = self.individual_roles_by_parameter or {}
        for parameter in self.parameters:
            argument_holder = simulation.compute(parameter, requested_columns_name = requested_columns_name)
            arguments_holder.append(argument_holder)
            argument = argument_holder.array
            individual_roles = individual_roles_by_parameter.get(parameter)
            if individual_roles is not None:
                # TODO Remove this and _option and replace with a call to function transform_column_from_entity_to_individu in formula function.
                assert entity.symbol != 'ind', str((column.name, parameter, entity.symbol))
                argument_extract_by_individual_role = {}
                parameter_column = tax_benefit_system.column_by_name[parameter]
                for individual_role in individual_roles:
                    argument_extract = np.empty(entity.count, dtype = parameter_column._dtype)
                    argument_extract.fill(parameter_column._default)
                    entity_index_array = individus.holder_by_name['id' + entity.symbol].array
                    boolean_filter = individus.holder_by_name['qui' + entity.symbol].array == individual_role
                    try:
                        argument_extract[entity_index_array[boolean_filter]] = argument[boolean_filter]
                    except:
                        log.error(
                            u'An error occurred while transforming column {} for role {}[{}] in function {}'.format(
                            parameter, entity.key_singular, individual_role, column.name))
                        raise
                    argument_extract_by_individual_role[individual_role] = argument_extract
                if len(individual_roles) == 1:
                    argument = argument_extract_by_individual_role[individual_roles[0]]
                else:
                    argument = argument_extract_by_individual_role
            arguments[parameter] = argument

        if self.requires_default_legislation:
            required_parameters.add('_defaultP')
            arguments['_defaultP'] = simulation.default_compact_legislation
        if self.requires_legislation:
            required_parameters.add('_P')
            arguments['_P'] = simulation.compact_legislation
        if self.requires_self:
            required_parameters.add('self')
            arguments['self'] = self

        provided_parameters = set(arguments.keys())
        assert provided_parameters == required_parameters, 'Formula {} requires missing parameters : {}'.format(
            u', '.join(sorted(required_parameters - provided_parameters)).encode('utf-8'))

        if simulation.debug:
            log.info(u'--> {}.{}({})'.format(entity.key_plural, column.name,
                get_arguments_str(arguments_holder)))
        try:
            array = self.calculate(**arguments)
        except:
            log.error(u'An error occurred while calling function {}.{}({})'.format(entity.key_plural, column.name,
                get_arguments_str(arguments_holder)))
            raise
        assert isinstance(array, np.ndarray), u"Function {}.{}({}) doesn't return a numpy array, but: {}".format(
            entity.key_plural, column.name, get_arguments_str(arguments_holder), array).encode('utf-8')
        assert array.size == entity.count, \
            u"Function {}.{}({}) returns an array of size {}, but size {} is expected for {}".format(entity.key_plural,
            column.name, get_arguments_str(arguments_holder), array.size, entity.count,entity.key_singular).encode(
            'utf-8')
        if array.dtype != column._dtype:
            array = array.astype(column._dtype)
        if simulation.debug:
            log.info(u'<-- {}.{}: {}'.format(entity.key_plural, column.name, array))
        holder.array = array
        requested_columns_name.remove(holder.column.name)
        return holder


def get_arguments_str(arguments_holder):
    return u', '.join(
        u'{} = {}.{}'.format(argument_holder.column.name, argument_holder.entity.key_plural,
            unicode(argument_holder.array))
        for argument_holder in arguments_holder
        )