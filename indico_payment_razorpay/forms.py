# This file is part of the Indico plugins.
# Copyright (C) 2017 - 2021 Max Fischer, Martin Claus, CERN
#
# The Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License;
# see the LICENSE file for more details.

import re

from wtforms.fields import StringField,IntegerField
from wtforms.fields.html5 import URLField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from indico.modules.events.payment import PaymentEventSettingsFormBase, PaymentPluginSettingsFormBase
from indico.web.forms.fields import IndicoPasswordField
from indico.web.forms.validators import IndicoRegexp

from indico_payment_razorpay import _


# XXX: Maybe this could be refactored to use the standard indico Placeholder system?
class FormatField:
    """Validator for format fields, i.e. strings with ``{key}`` placeholders.

    :param max_length: optional maximum length, checked on a test formatting
    :param field_map: keyword arguments to use for test formatting

    On validation, a test mapping is applied to the field. This ensures the
    field has a valid ``str.format`` format, and does not use illegal keys
    (as determined by ``default_field_map`` and ``field_map``).
    The ``max_length`` is validated against the test-formatted field, which
    is an estimate for an average sized input.
    """

    #: default placeholders to test length after formatting
    default_field_map = {
        'user_id': 12345,
        'user_name': 'Jane Whiteacre',
        'user_firstname': 'Jane',
        'user_lastname': 'Whiteacre',
        'event_id': 12345,
        'event_title': 'Placeholder: The Event',
        'registration_id': 12345,
        'regform_title': 'EarlyBird Registration'
    }

    #: id-safe placeholders to test length after formatting
    id_safe_field_map = {
        'user_id': 12345,
        'event_id': 12345,
        'registration_id': 12345,
    }

    def __init__(self, max_length=float('inf'), id_safe=False):
        """Format field validator, i.e. strings with ``{key}`` placeholders.

        :param max_length: optional maximum length,
                           checked on a test formatting
        :param field_map: keyword arguments to use for test formatting
        :param id_safe: only allow fields safe for a saferpay id argument
        """
        self.max_length = max_length
        self.id_safe = id_safe
        self.field_map = self.id_safe_field_map if id_safe else self.default_field_map

    def __call__(self, form, field):
        """Validate format field data.

        Returns true on successful validation, else an ValidationError is
        thrown.
        """
        if not field.data:
            return True
        try:
            test_format = field.data.format(**self.field_map)
        except KeyError as exc:
            raise ValidationError(_('Invalid format string key: {}').format(exc))
        except ValueError as exc:
            raise ValidationError(_('Malformed format string: {}').format(exc))
        if len(test_format) > self.max_length:
            raise ValidationError(
                _('Format string too long: shortest replacement with {len}, expected {max}')
                .format(len=len(test_format), max=self.max_length)
            )
        if self.id_safe and not re.match(r'^[A-Za-z0-9.:_-]+$', test_format):
            raise ValidationError(_('This field may only contain alphanumeric chars, dots, colons, '
                                    'hyphens and underscores.'))
        return True


class PluginSettingsForm(PaymentPluginSettingsFormBase):
    """Configuration form for the Plugin across all events."""

    markup = IntegerField(
        label=_('Payment Gateway Markup'),
        validators=[DataRequired()],
        description=_('increase the final amount by specified percentage amount to factor in Razorpay markup. 1% = 1000 ')
    )
    username = StringField(
        label=_('API Key ID'),
        validators=[DataRequired()],
        description=_('The API Key ID to access the Razorpay API')
    )
    password = IndicoPasswordField(
        label=_('API Secret Key'),
        validators=[DataRequired()],
        description=_('The Secret Key to access the Razorpay API'),
        toggle=True,
    )
    org_name = StringField(
        _('Organizer name'),
        [Optional()],
        default='Organization',
        description=_('Name of the event organizer')
    )
    order_description = StringField(
        label=_('Order Description'),
        validators=[DataRequired(), FormatField(max_length=80)],
        description=_(
            'The default description of each order in a human readable way. '
            'It is presented to the registrant during the transaction with Saferpay. '
            'Event managers will be able to override this. '
            'Supported placeholders: {}'
        ).format(', '.join(f'{{{p}}}' for p in FormatField.default_field_map))
    )
    order_identifier = StringField(
        label=_('Order Identifier'),
        validators=[DataRequired(), FormatField(max_length=80)],
        description=_(
            'The default description of each order in a human readable way. '
            'It is presented to the registrant during the transaction with Saferpay. '
            'Event managers will be able to override this. '
            'Supported placeholders: {}'
        ).format(', '.join(f'{{{p}}}' for p in FormatField.default_field_map))
    )
    notification_mail = StringField(
        label=_('Notification Email'),
        validators=[Optional(), Email(), Length(0, 50)],
        description=_(
            'Email address to receive notifications of transactions. '
            "This is independent of Indico's own payment notifications. "
            'Event managers will be able to override this.'
        )
    )

class EventSettingsForm(PaymentEventSettingsFormBase):
    """Configuration form for the plugin for a specific event."""

    order_description = StringField(
        label=_('Order Description'),
        validators=[DataRequired(), FormatField(max_length=80)],
        description=_(
            'The description of each order in a human readable way. '
            'It is presented to the registrant during the transaction with Saferpay. '
            'Supported placeholders: {}'
        ).format(', '.join(f'{{{p}}}' for p in FormatField.default_field_map))
    )
    order_identifier = StringField(
        label=_('Order Identifier'),
        validators=[DataRequired(), FormatField(max_length=80, id_safe=True)],
        description=_(
            'The default identifier of each order for further processing. '
            'Supported placeholders: {}'
        ).format(', '.join(f'{{{p}}}' for p in FormatField.id_safe_field_map))
    )
    notification_mail = StringField(
        label=_('Notification Email'),
        validators=[DataRequired(), Email(), Length(0, 50)],
        description=_(
            'Email address to receive notifications of transactions. '
            "This is independent of Indico's own payment notifications."
        )
    )
